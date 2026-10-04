assets 目录说明
===============

放自定义素材：

1) app.ico
   - 应用图标：任务栏、窗口左上角、Alt+Tab
   - 必须是 .ico 格式，建议 256×256
   - 没有则尝试 app.png

2) app.png
   - 备用图标，256×256 透明底 PNG

3) welcome.png（或 welcome.gif / welcome.jpg / welcome.jpeg 都行）
   - 首页居中显示的大图，建议 200×200 到 400×400 方形
   - GIF 只显示第一帧
   - 没有则使用内置logo

注意事项
--------
· 修改后重启程序生效（Windows 任务栏图标有缓存）
· 文件名严格区分大小写
· 加载失败会自动回退到内置图标，不报错