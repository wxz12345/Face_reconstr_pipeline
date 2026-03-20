#!/bin/bash

# ==========================================
# 1. 基础配置 (统一参数入口)
# ==========================================
# 执行方式: ./run_all.sh obama 0 60001
SEQUENCE=${1}   # 序列名
GPU_ID=${2}         # GPU 编号
PORT=${3- "60000"}       # 训练可视化端口

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
DATA_ROOT="upload"
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
WEB_ROOT="../web_runner"

# 1. 自动定位并初始化 conda（这一步很重要）
CONDA_PATH=$(conda info --base)
source "$CONDA_PATH/etc/profile.d/conda.sh"

conda activate pipe

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
cd ../VHAP || { echo "无法进入VHAP目录"; exit 1; }

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
    echo ">>> [Step 1/5] 正在进行视频预处理..."
    python vhap/preprocess_video.py \
        --input "${WEB_ROOT}/${DATA_ROOT}/${SEQUENCE}.mp4" \
        --matting_method robust_video_matting || { echo "Step 1 失败"; exit 1; }
else
    echo ">>> [Step 1/5] 跳过预处理（目录已存在）。"
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
    echo ">>> [Step 2/5] 正在运行追踪程序..."
    python vhap/track.py \
        --data.root_folder "${WEB_ROOT}/${DATA_ROOT}" \
        --exp.output_folder "${WEB_ROOT}/${TRACK_OUTPUT_FOLDER}" \
        --data.sequence "$SEQUENCE" || { echo "Step 2 失败"; exit 1; }
else
    echo ">>> [Step 2/5] 跳过追踪（目录已存在）。"
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
    echo ">>> [Step 3/5] 正在导出为 NeRF 数据集格式..."
    python vhap/export_as_nerf_dataset.py \
        --src_folder "${WEB_ROOT}/${TRACK_OUTPUT_FOLDER}" \
        --tgt_folder "${WEB_ROOT}/${EXPORT_OUTPUT_FOLDER}" \
        --background-color white || { echo "Step 3 失败"; exit 1; }
else
    echo ">>> [Step 3/5] 跳过导出（目录已存在）。"
fi

# ==========================================
# 3. 项目2: 训练 (GSA)
# ==========================================
# 进入GaussianAvatars目录并执行训练
cd ../GaussianAvatars || { echo "无法进入GaussianAvatars目录"; exit 1; }

echo ">>> [Step 4/5] 开始训练..."
# 注意：这里直接使用了项目1产生的 EXPORT_OUTPUT_FOLDER
python ./train.py \
    -s "${WEB_ROOT}/${TRAIN_DATA_PATH}" \
    -m "${WEB_ROOT}/${TRAIN_OUTPUT_PATH}" \
    --eval \
    --bind_to_mesh \
    --white_background \
    --port "$PORT" || { echo "训练失败"; exit 1; }

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

cd ../web_runner || { echo "无法进入web_runner目录"; exit 1; }

echo ">>> [Step 5/5] 开始打包..."

python 


# # 定义最终 Zip 存放在哪里（比如放在 results/video_01 目录下）
# FINAL_ZIP_PATH="${RESULTS_BASE}/zip_res/${SEQUENCE}.zip"

# # --- 2. 在 output 文件夹内生成 summary.txt ---
# # 既然不打算删 tmp，直接写在 output 里也是一样的
# SUMMARY_PATH="${TRAIN_OUTPUT_PATH}/summary.txt"
# TS=$(date "+%Y-%m-%d %H:%M:%S")

# cat <<EOF > "$SUMMARY_PATH"
# Input video: ./upload/${SEQUENCE}
# Processed at: $TS
# Status: success
# Sequence ID: $SEQUENCE
# EOF

# # --- 3. 执行打包 ---
# # 我们使用 ( ) 开启子 Shell，这样 cd 命令不会改变你当前主脚本的工作目录
# echo "Zipping output folder to $FINAL_ZIP_PATH..."
# (
#     cd "$TRAIN_OUTPUT_PATH" || exit
#     # 将当前目录 (.) 下的所有内容压缩到目标路径
#     # -r 表示递归压缩子目录
#     zip -r "../../$(basename "$FINAL_ZIP_PATH")" ./*
# )

# echo "Done! Zip created at: $FINAL_ZIP_PATH"