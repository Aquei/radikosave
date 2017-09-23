# Radikosave
[radiko.jp](http://radiko.jp/)のタイムフリーを保存する

## 事前準備
* Java実行環境
* ffmpeg
* [Firefox](https://www.mozilla.org/ja/firefox/) ( Fx55+ on Linux, and 56+ on Windows/Mac )
* [geckodriver](https://github.com/mozilla/geckodriver/releases)
* [python](https://www.python.org/) 3.5+
* [BrowserMob Proxy](https://github.com/lightbody/browsermob-proxy/releases)
* pip, virtualenv

ffmpeg, geckodriverをPATHの通ったところに置く  
[virtualenv](https://docs.python.jp/3/library/venv.html)で仮想環境を作る  
pipでパッケージをインストールする  
```sh
#!/bin/bash
source myenv/bin/activate
pip3 install -r requirements.txt
```

## 利用方法
`radikosave.py [-h] [-p PATH] [-c CODEC] [-q QUALITY] [-e EXTENTION] urls [urls ...]`

### 引数
* -h ヘルプ
* -p BrowserMob Proxyの実行ファイルのパス PATHにある場合は省略
* -c 保存する際のコーデック (エンコードしない場合は省略)
* -q 保存する際の圧縮品質(ffmpegに渡す)
* -e ファイルコンテナの拡張子 (デフォルト: m4a)
* urls <http://radiko.jp/#!/ts/QRR/20170924060000> みたいなタイムフリーの再生ページ　スペース区切りで複数指定可


