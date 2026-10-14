@echo off
chcp 65001 > nul
echo 正在提交修改到 GitHub...

git add .
git commit -m "Auto update: %date% %time%"
git push origin main

echo.
echo 更新完成！
pause