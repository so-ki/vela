#!/usr/bin/env bash
# 在 macOS 桌面创建「Vela 出海法务」双击启动快捷方式（.app）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APP_NAME="Vela 出海法务.app"
DESKTOP="${HOME}/Desktop"
TARGET="${DESKTOP}/${APP_NAME}"
MACOS_DIR="${TARGET}/Contents/MacOS"
RES_DIR="${TARGET}/Contents/Resources"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "此脚本仅适用于 macOS。"
  exit 1
fi

echo "==> 安装桌面快捷方式"
echo "    项目目录: ${ROOT}"
echo "    目标位置: ${TARGET}"

rm -rf "${TARGET}"
mkdir -p "${MACOS_DIR}" "${RES_DIR}"

cat > "${TARGET}/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key>
  <string>zh_CN</string>
  <key>CFBundleExecutable</key>
  <string>vela-launcher</string>
  <key>CFBundleIdentifier</key>
  <string>com.vela.platform.local</string>
  <key>CFBundleName</key>
  <string>Vela</string>
  <key>CFBundleDisplayName</key>
  <string>Vela 出海法务</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>LSMinimumSystemVersion</key>
  <string>11.0</string>
  <key>NSHighResolutionCapable</key>
  <true/>
</dict>
</plist>
PLIST

cat > "${MACOS_DIR}/vela-launcher" <<LAUNCHER
#!/usr/bin/env bash
VELA_ROOT="${ROOT}"

if [[ ! -d "\${VELA_ROOT}" ]]; then
  osascript -e 'display alert "Vela 未找到" message "项目目录不存在，请重新运行 scripts/macos/install_desktop_shortcut.sh" as critical'
  exit 1
fi

osascript <<APPLESCRIPT
tell application "Terminal"
  activate
  if not (exists window 1) then reopen
  do script "cd \\"${ROOT}\\" && ./scripts/start.sh"
end tell
APPLESCRIPT
LAUNCHER

chmod +x "${MACOS_DIR}/vela-launcher"

echo ""
echo "已创建: ${TARGET}"
echo "用法: 在桌面双击「Vela 出海法务」→ 自动打开终端并启动服务 → 浏览器会打开 http://127.0.0.1:5173"
echo "停止: 在终端窗口按 Ctrl+C"
echo ""
echo "若移动了项目文件夹，请重新运行: ${ROOT}/scripts/macos/install_desktop_shortcut.sh"
