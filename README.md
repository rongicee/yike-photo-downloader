# 一刻相册下载工具

百度一刻相册批量下载工具，支持：
- 只下载图片，稳定不卡顿
- 自动导出所有视频 FSID 列表
- 单任务串行下载
- 依赖Aria2服务器
- Web 面板可视化操作

## 使用方法
1. 填写 settings.json
2. 安装依赖：pip install -r requirements.txt
3. 运行：python main.py
4. 打开浏览器：http://localhost:7892

TIPS:
由于一刻相册的限制，目前最新视频文件已经是有m3u8切片来索引，故本项目放弃了对视频的下载，望知悉！
