#!/bin/bash
# 打包九儿桌面宠物为 macOS .app
# 使用 Chrome app mode 实现无边框透明窗口效果

APP_NAME="九儿桌面宠物"
APP_DIR="$APP_NAME.app"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HTML_PATH="$SCRIPT_DIR/jiuer-pet.html"

# 创建 .app 目录结构
mkdir -p "$APP_DIR/Contents/MacOS"
mkdir -p "$APP_DIR/Contents/Resources"

# 写入 Info.plist
cat > "$APP_DIR/Contents/Info.plist" << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleExecutable</key>
  <string>launcher</string>
  <key>CFBundleName</key>
  <string>九儿桌面宠物</string>
  <key>CFBundleIdentifier</key>
  <string>com.jiuer.desktop-pet</string>
  <key>CFBundleVersion</key>
  <string>2.1</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>LSUIElement</key>
  <true/>
  <key>LSBackgroundOnly</key>
  <true/>
</dict>
</plist>
EOF

# 写入启动脚本（用 Chrome app mode 实现无边框窗口）
cat > "$APP_DIR/Contents/MacOS/launcher" << EOF
#!/bin/bash
HTML="file://$HTML_PATH"
# 尝试 Chrome app mode（无边框）
if [ -d "/Applications/Google Chrome.app" ]; then
  open -na "Google Chrome" --args --app="\$HTML" --window-size=240,260 --window-position=100,100
elif [ -d "/Applications/Microsoft Edge.app" ]; then
  open -na "Microsoft Edge" --args --app="\$HTML" --window-size=240,260 --window-position=100,100
else
  # 回退到默认浏览器
  open "\$HTML"
fi
EOF

chmod +x "$APP_DIR/Contents/MacOS/launcher"

echo "✅ 已打包: $APP_DIR"
echo "双击运行即可"
echo ""
echo "提示："
echo "1. 如果 Chrome 提示"允许来自 unidentified developer"，请前往 系统设置 > 隐私与安全性 允许"
echo "2. 或右键点击 .app → 打开"
