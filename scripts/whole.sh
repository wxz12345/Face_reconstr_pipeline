#!/bin/bash

# ==========================================
# 1. 基础配置 (统一参数入口)
# ==========================================
# 执行方式: ./run_all.sh obama 0 60001
SEQUENCE=${1}   # 序列名
GPU_ID=${2}         # GPU 编号
PORT=${3- "60000"}       # 训练可视化端口

# SUFFIX='_test'
SUFFIX=''

# 锁定 GPU
export CUDA_VISIBLE_DEVICES=$GPU_ID

# --- 项目1 路径定义 ---
# DATA_ROOT="./upload"
# TRACK_BASE="./results/track"
# EXPORT_BASE="./results/export"

# SEQ_DATA_DIR="${DATA_ROOT}/${SEQUENCE}"
# TRACK_OUTPUT_FOLDER="${TRACK_BASE}/${SEQUENCE}"
# # 这是项目1生成的最终数据集目录
# EXPORT_OUTPUT_FOLDER="${EXPORT_BASE}/${SEQUENCE}"

# # --- 项目2 路径定义 ---
# # 我们直接将项目1的导出目录作为项目2的输入
# TRAIN_DATA_PATH="${EXPORT_OUTPUT_FOLDER}" 
# TRAIN_OUTPUT_PATH="./output/${SEQUENCE}"

# --- 基础定义 ---
DATA_ROOT="uploads"
# 所有的结果现在都以序列名作为主文件夹
RESULTS_BASE="results/${SEQUENCE}"

# --- 项目1 路径定义 ---
SEQ_DATA_DIR="${DATA_ROOT}/${SEQUENCE}"
# 修改后：./results/video_01/track
TRACK_OUTPUT_FOLDER="${RESULTS_BASE}/track"
# 修改后：./results/video_01/export
EXPORT_OUTPUT_FOLDER="${RESULTS_BASE}/export"

# --- 项目2 路径定义 ---
TRAIN_DATA_PATH="${EXPORT_OUTPUT_FOLDER}" 
# 修改后：./results/video_01/output
TRAIN_OUTPUT_PATH="${RESULTS_BASE}/output"


# --- web 路径定义 ---
WEB_ROOT=$(readlink -f "../web_runner")

# 1. 自动定位并初始化 conda（这一步很重要）
echo "[INFO] Initializing runtime environment"
echo "[DEBUG] Initial cwd: $(pwd)"
echo "[DEBUG] SEQUENCE=${SEQUENCE}, GPU_ID=${GPU_ID}, PORT=${PORT}, SUFFIX=${SUFFIX}"
echo "[DEBUG] WEB_ROOT=${WEB_ROOT}"
echo "[DEBUG] TRAIN_OUTPUT_PATH=${TRAIN_OUTPUT_PATH}"
CONDA_PATH=$(conda info --base)
source "$CONDA_PATH/etc/profile.d/conda.sh"
echo "[DEBUG] CONDA_PATH=${CONDA_PATH}"

conda activate pipe
echo "[INFO] Conda environment activated: pipe"

START_TIME=$(date +%s)
echo "=========================================="
echo "开始全流程处理: ${SEQUENCE}"
echo "使用 GPU: ${GPU_ID} | 端口: ${PORT}"
echo "开始时间: $(date "+%Y-%m-%d %H:%M:%S")"
echo "=========================================="

# ==========================================
# 2. 项目1: 预处理与追踪 (VHAP)
# ==========================================
# 进入VHAP目录并执行预处理
echo "[INFO] Entering VHAP stage"
cd ../VHAP || { echo "无法进入VHAP目录"; exit 1; }
echo "[DEBUG] VHAP cwd: $(pwd)"

# Step 1: 视频 -> 图片

# 输入 (Input):
# 路径：${DATA_ROOT}/${SEQUENCE}.mp4 (例如：data/monocular/obama.mp4)
# 内容：一段原始的 RGB 视频文件。
# 处理逻辑:
# 使用 robust_video_matting 模型对视频进行抠图。
# 将视频按帧拆解为单张图片。
# 输出 (Output):
# 路径：${SEQ_DATA_DIR}/images/ (例如：data/monocular/obama/images/)
# 文件：00001.png, 00002.png ... (高像素图片)
# 隐式输出： 通常还会生成对应的掩码文件夹 masks/。

if [ ! -d "${WEB_ROOT}/${DATA_ROOT}/${SEQUENCE}/images" ]; then
    echo "[INFO] [Step 1/5] Starting preprocess"
    echo "[DEBUG] Step 1 input: ${WEB_ROOT}/${DATA_ROOT}/${SEQUENCE}.mp4"
    echo "[DEBUG] Step 1 output dir: ${WEB_ROOT}/${DATA_ROOT}/${SEQUENCE}/images"
    python vhap/preprocess_video${SUFFIX}.py \
        --input "${WEB_ROOT}/${DATA_ROOT}/${SEQUENCE}.mp4" \
        --matting_method robust_video_matting || { echo "[ERROR] Step 1 failed"; exit 1; }
    echo "[INFO] [Step 1/5] Preprocess finished"
else
    echo "[INFO] [Step 1/5] Skip preprocess (output already exists)"
fi

# Step 2: 追踪

# 输入 (Input):
# 路径：${DATA_ROOT}/${SEQUENCE} (指向刚才生成的图片目录)。
# 内容：Step 1 生成的图片序列和掩码。
# 处理逻辑:
# 分析每一帧图片，推算摄像机位姿 (Camera Pose)。
# 推算人脸/头部的 3D 形状、表情系数 (Expression) 和旋转位姿。
# 输出 (Output):
# 路径：${TRACK_OUTPUT_FOLDER} (例如：output/monocular/obama_whiteBg_staticOffset/)
# 文件：通常包含 track_params.pt 或大量的 .json/.npz 文件，记录了每一帧的 3D 状态（旋转、平移、表情参数）。
# 注意： 这里的输出还不能直接给训练程序用，因为它是项目特有的中间格式。

if [ ! -d "./${WEB_ROOT}/${TRACK_OUTPUT_FOLDER}" ]; then
    echo "[INFO] [Step 2/5] Starting tracking"
    echo "[DEBUG] Step 2 root folder: ${WEB_ROOT}/${DATA_ROOT}"
    echo "[DEBUG] Step 2 output folder: ${WEB_ROOT}/${TRACK_OUTPUT_FOLDER}"
    python vhap/track${SUFFIX}.py \
        --data.root_folder "${WEB_ROOT}/${DATA_ROOT}" \
        --exp.output_folder "${WEB_ROOT}/${TRACK_OUTPUT_FOLDER}" \
        --data.sequence "$SEQUENCE" || { echo "[ERROR] Step 2 failed"; exit 1; }
    echo "[INFO] [Step 2/5] Tracking finished"
else
    echo "[INFO] [Step 2/5] Skip tracking (output already exists)"
fi

# Step 3: 导出 NeRF 格式

# 输入 (Input):
# 路径：${TRACK_OUTPUT_FOLDER} (Step 2 的输出目录)。
# 内容：那些复杂的 3D 追踪参数和原始图片。
# 处理逻辑:
# 将 Step 2 的追踪参数转换成标准的 NeRF 格式（通常是 Gaussian Splatting 能读懂的格式）。
# 统一背景色（例如 --background-color white）。
# 生成相机内参、外参的标准化描述文件。
# 输出 (Output):
# 路径：${EXPORT_OUTPUT_FOLDER} (例如：export/monocular/obama_whiteBg_staticOffset_maskBelowLine/)
# 核心结构：
# images/: 处理后的图片（可能缩放过或处理过背景）。
# masks/: 对应的掩码图片。
# transforms.json: 这是最关键的接口文件。它记录了所有图片的路径以及对应的相机焦距、旋转矩阵、平移向量。

# cd ../end2end_rec || { echo "无法进入end2end_rec目录"; exit 1; }

if [ ! -d "${WEB_ROOT}/${EXPORT_OUTPUT_FOLDER}" ]; then
    echo "[INFO] [Step 3/5] Starting NeRF export"
    echo "[DEBUG] Step 3 source: ${WEB_ROOT}/${TRACK_OUTPUT_FOLDER}"
    echo "[DEBUG] Step 3 target: ${WEB_ROOT}/${EXPORT_OUTPUT_FOLDER}"
    python vhap/export_as_nerf_dataset${SUFFIX}.py \
        --src_folder "${WEB_ROOT}/${TRACK_OUTPUT_FOLDER}" \
        --tgt_folder "${WEB_ROOT}/${EXPORT_OUTPUT_FOLDER}" \
        --background-color white || { echo "[ERROR] Step 3 failed"; exit 1; }
    echo "[INFO] [Step 3/5] NeRF export finished"
else
    echo "[INFO] [Step 3/5] Skip NeRF export (output already exists)"
fi

# ==========================================
# 3. 项目2: 训练 (GSA)
# ==========================================
# 进入GaussianAvatars目录并执行训练
echo "[INFO] Entering GaussianAvatars stage"
cd ../GaussianAvatars || { echo "无法进入GaussianAvatars目录"; exit 1; }
echo "[DEBUG] GaussianAvatars cwd: $(pwd)"

echo "[INFO] [Step 4/5] Starting training"
echo "[DEBUG] Step 4 data path: ${WEB_ROOT}/${TRAIN_DATA_PATH}"
echo "[DEBUG] Step 4 model path: ${WEB_ROOT}/${TRAIN_OUTPUT_PATH}"
# 注意：这里直接使用了项目1产生的 EXPORT_OUTPUT_FOLDER
python ./train${SUFFIX}.py \
    -s "${WEB_ROOT}/${TRAIN_DATA_PATH}" \
    -m "${WEB_ROOT}/${TRAIN_OUTPUT_PATH}" \
    --eval \
    --bind_to_mesh \
    --white_background \
    --port "$PORT" || { echo "[ERROR] Training failed"; exit 1; }
echo "[INFO] [Step 4/5] Training finished"

# ==========================================
# 4. 结束总结
# ==========================================
END_TIME=$(date +%s)
ELAPSED_TIME=$((END_TIME - START_TIME))

echo "=========================================="
echo "主要流程执行完毕！"
echo "数据目录: ${TRAIN_DATA_PATH}"
echo "模型目录: ${TRAIN_OUTPUT_PATH}"
echo "总耗时: $(($ELAPSED_TIME / 3600))小时$((($ELAPSED_TIME % 3600) / 60))分钟$(($ELAPSED_TIME % 60))秒"
echo "=========================================="

echo "[INFO] Entering packaging stage"
cd ../web_runner || { echo "无法进入web_runner目录"; exit 1; }
echo "[DEBUG] Packaging cwd: $(pwd)"

echo "[INFO] [Step 5/5] Starting zip packaging"

command -v zip >/dev/null 2>&1 || { echo "[ERROR] zip command not found"; exit 1; }

WEB_ROOT_DIR="$(pwd)"
ZIP_DIR="${WEB_ROOT_DIR}/results/zip_res"
SRC_DIR="${WEB_ROOT_DIR}/${TRAIN_OUTPUT_PATH}"
FINAL_ZIP_PATH="${ZIP_DIR}/${SEQUENCE}.zip"

mkdir -p "${ZIP_DIR}"
if [ ! -d "${SRC_DIR}" ]; then
    echo "[ERROR] Output directory not found: ${SRC_DIR}"
    exit 1
fi

rm -f "${FINAL_ZIP_PATH}"

echo "[DEBUG] ZIP_DIR=${ZIP_DIR}"
echo "[DEBUG] SRC_DIR=${SRC_DIR}"
echo "[DEBUG] FINAL_ZIP_PATH=${FINAL_ZIP_PATH}"
echo "[INFO] Zipping ${SRC_DIR} -> ${FINAL_ZIP_PATH}"
(
    cd "${SRC_DIR}" || exit 1
    zip -r -9 "${FINAL_ZIP_PATH}" . || exit 1
) || { echo "[ERROR] Zip creation failed"; exit 1; }

echo "[INFO] [Step 5/5] Zip packaging finished"
echo "[INFO] Zip created at: ${FINAL_ZIP_PATH}"
