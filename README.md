# 一刻相册下载工具

百度一刻相册批量下载工具，支持：
- 只下载图片，稳定不卡顿
- 自动导出所有视频 FSID 列表
- 单任务串行下载
- 依赖Aria2服务器
- Web 面板可视化操作

## 使用方法
## 🐳 Docker 部署（推荐）

1. 在项目根目录执行：
docker build -t yike-photo-downloader .
2. 运行容器
docker run -d \
  --name yike-photo \
  -p 7989:7989 \
  -v 你的路径/downloads:/download \
  -v 你的路径:/app \
  --restart always \
  yike-photo-downloader
3. 填写 settings.json
4. 访问面板
打开浏览器访问：
http://localhost:7989

TIPS:
由于一刻相册的限制，目前最新视频文件已经是有m3u8切片来索引，故本项目放弃了对视频的下载，望知悉！
