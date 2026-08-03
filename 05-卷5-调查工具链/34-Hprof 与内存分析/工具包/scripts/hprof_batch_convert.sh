#!/bin/bash
# hprof 批量转换脚本(Linux/Mac)
# 把 Android binary hprof 批量转换为标准 Java HPROF
#
# 用法:
#   ./hprof_batch_convert.sh                    # 转换当前目录所有 .hprof
#   ./hprof_batch_convert.sh /path/to/hprof/    # 转换指定目录
#   ./hprof_batch_convert.sh file1.hprof file2  # 转换指定文件
#
# 依赖:hprof-conv(Android SDK platform-tools)
#   - Linux: ~/Android/Sdk/platform-tools/hprof-conv
#   - Mac: ~/Library/Android/sdk/platform-tools/hprof-conv
#
# 配套文档:Android_Framework_Layer/Hprof/02-hprof解析工具链.md §2.2

set -e

# ====== 配置 ======
HPROF_CONV="${HPROF_CONV:-$(which hprof-conv 2>/dev/null || echo "$HOME/Android/Sdk/platform-tools/hprof-conv")}"
INPUT_DIR="${1:-.}"
OUTPUT_SUFFIX="_converted"

# ====== 颜色输出 ======
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# ====== 检查 hprof-conv ======
if [ ! -x "$HPROF_CONV" ]; then
    echo -e "${RED}✗ hprof-conv 未找到${NC}"
    echo "  请设置环境变量 HPROF_CONV 指向 hprof-conv 路径"
    echo "  或把 hprof-conv 加入 PATH"
    echo ""
    echo "  默认路径:"
    echo "    Linux: ~/Android/Sdk/platform-tools/hprof-conv"
    echo "    Mac:   ~/Library/Android/sdk/platform-tools/hprof-conv"
    echo ""
    exit 1
fi

# ====== 收集 hprof 文件 ======
if [ -d "$INPUT_DIR" ]; then
    # 目录模式:递归查找所有 .hprof
    HPROF_FILES=$(find "$INPUT_DIR" -name "*.hprof" -type f)
elif [ -f "$INPUT_DIR" ]; then
    # 单文件模式
    HPROF_FILES="$INPUT_DIR"
    shift
    # 加上其余参数指定的文件
    while [ $# -gt 0 ]; do
        HPROF_FILES="$HPROF_FILES $1"
        shift
    done
else
    echo -e "${RED}✗ 输入路径无效: $INPUT_DIR${NC}"
    exit 1
fi

if [ -z "$HPROF_FILES" ]; then
    echo -e "${YELLOW}⚠ 未找到 .hprof 文件${NC}"
    exit 0
fi

# ====== 批量转换 ======
TOTAL=0
SUCCESS=0
FAILED=0

echo -e "${GREEN}=== hprof 批量转换 ===${NC}"
echo "工具路径: $HPROF_CONV"
echo "输入: $INPUT_DIR"
echo ""

for INPUT_FILE in $HPROF_FILES; do
    TOTAL=$((TOTAL + 1))
    
    # 跳过已经是 _converted 的文件
    BASENAME=$(basename "$INPUT_FILE")
    if [[ "$BASENAME" == *"$OUTPUT_SUFFIX.hprof" ]]; then
        echo -e "${YELLOW}⊘ 跳过(已转换): $BASENAME${NC}"
        continue
    fi
    
    # 输出文件
    DIRNAME=$(dirname "$INPUT_FILE")
    OUTPUT_FILE="${DIRNAME}/${BASENAME%.hprof}${OUTPUT_SUFFIX}.hprof"
    
    echo -n "[$TOTAL] $BASENAME ... "
    
    # 执行转换
    if "$HPROF_CONV" "$INPUT_FILE" "$OUTPUT_FILE" 2>/dev/null; then
        INPUT_SIZE=$(du -h "$INPUT_FILE" | cut -f1)
        OUTPUT_SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)
        echo -e "${GREEN}✓ 成功${NC} ($INPUT_SIZE → $OUTPUT_SIZE)"
        SUCCESS=$((SUCCESS + 1))
    else
        echo -e "${RED}✗ 失败${NC}"
        FAILED=$((FAILED + 1))
    fi
done

# ====== 汇总 ======
echo ""
echo -e "${GREEN}=== 汇总 ===${NC}"
echo "总计: $TOTAL"
echo "成功: $SUCCESS"
echo "失败: $FAILED"

if [ $FAILED -gt 0 ]; then
    echo ""
    echo -e "${YELLOW}⚠ 部分文件转换失败,常见原因:${NC}"
    echo "  1. 文件损坏(重新 dump)"
    echo "  2. hprof-conv 版本过旧(更新 Android SDK)"
    echo "  3. ID size 不匹配(尝试用其他工具)"
    exit 1
fi

exit 0