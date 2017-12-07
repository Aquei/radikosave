#!/usr/bin/env python3
from browsermobproxy import Server
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.common.exceptions import TimeoutException as STimeoutException
from pathlib import Path
from urllib.parse import urlparse
import time
from datetime import timedelta, datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import selenium.common.exceptions
from collections import namedtuple
import re
import os
import subprocess
import argparse
from math import ceil
import concurrent.futures

class Radikosave():
    """メインクラス"""

    def __init__(self, urls=None, codec='copy', quality=4, extention='m4a', bmp_path=None, max_workers=1):
        self._driver = None
        self._proxy = None
        self._server = None
        if urls is None:
            self.urls = []
        else:
            self.urls = urls
        self.codec = codec
        self.quality = quality
        self.extention = extention
        self.bmp_path = bmp_path
        self.max_workers = max_workers

        
    def save_files(self):
        max_workers = self.max_workers
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}

            for url in self.urls:
                har, meta = self.get_har_and_meta(url, self.bmp_path)
                token, m3u8_url = self.get_playlist_info(har)

                future = executor.submit(self.save_file, meta, token, m3u8_url)
                futures[future] = url 


            for future in concurrent.futures.as_completed(futures):
                url = futures[future]

                try:
                    future.exception()

                except Exception as err:
                    raise err





    def save_file(self, meta, token, m3u8_url):
        """ファイルに保存"""
        
        has_ff, ffname = self.has_ffmpeg()

        if has_ff:
            filename = self.get_filename(meta)
            timeout = 60 * 60 * 3 #最大3時間待つ
            print("{}を保存中".format(filename))
            start = time.time()
            try:
                args = [
                        ffname,
                        '-hide_banner',
                        '-loglevel',
                        'fatal',
                        '-nostdin',
                        '-y',
                        '-headers',
                        'X-Radiko-AuthToken: ' + token,
                        '-i',
                        m3u8_url,
                        '-vn',
                        '-codec:a',
                        self.codec,
                        '-q:a',
                        str(self.quality),
                        filename
                ]
                cmplt = subprocess.run(args, check=True, timeout=timeout)

            except subprocess.TimeoutExpired as err:
                print("{filename}: {timeout}秒待ちましたが、処理が終了しませんでした エラー内容{err}".format(filename=filename,timeout=timeout, err=err.stderr))

            except subprocess.CalledProcessError as err:
                print("{filename}: 終了ステータス: {status} でプロセスが終了しました エラー内容{err}".format(status=err.returncode, err=err.stderr, filename=filename))

            else:
                est = int(ceil(time.time() - start))
                print("{}秒で{}を保存しました".format(est, filename))

        else:
            raise Exception("ffmpeg unavailable")

    def get_har_and_meta(self, url, path):
        """urlのharを返す"""

        parsed = urlparse(url)

        for i in range(2):
            if not parsed[i]:
                raise NotAURLError(url)

        proxy, server = self.get_proxy(path)
        driver = self.get_driver(proxy)

        id_ = parsed.netloc + str(time.time())
        id_ = id_.replace('.', '_').replace(':', '_') 

        har_options = {
                "captureHeaders": True
        }
        proxy.new_har(ref=id_, options=har_options)

        #再生
        meta = self.start_play(driver, url)

        har = proxy.har

        return har, meta

    def start_play(self, driver, url):
        """ページを開いて再生し、番組のメタ情報を返す"""

        #番組名と出演者、放送時刻を持つ名前付きtupleのクラス
        ProgramMeta = namedtuple('ProgramMeta', ['title', 'cast_name', 'time_start', 'time_end'], rename=True)

        driver.get(url)
        try:
            #title
            title_class_name = "live-detail__title"
            title = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CLASS_NAME, title_class_name))
            )
            meta_title = driver.find_element(By.CLASS_NAME, title_class_name).text.strip()

            #cast
            try:
                cast_class_name = "live-detail__cast-name"
                cast = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CLASS_NAME, cast_class_name))
                )
                meta_cast = driver.find_element(By.CLASS_NAME, cast_class_name).text.strip()

            except STimeoutException as e:
                cast_selector = ".live-detail__cast-title+div>div"
                cast = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, cast_selector))
                )
                meta_cast = driver.find_element(By.CSS_SELECTOR, cast_selector).text.strip()

            #time
            time_class_name = "live-detail__time"
            time_e = WebDriverWait(driver, 10).until(
                    EC.visibility_of_element_located((By.CLASS_NAME, time_class_name))
            )
            time_txt = driver.find_element(By.CLASS_NAME, time_class_name).text.strip()
            match = re.search('(?P<month>\d+)月(?P<day>\d+)日（(?P<j_d>.)）\s(?P<start_hour>\d{2}):(?P<start_min>\d{2})-(?P<end_hour>\d{2}):(?P<end_min>\d{2})', time_txt)
            if match:
                start_y = int(time.localtime().tm_year)
                start_m = int(match.group("month"))
                start_d = int(match.group("day"))
                start_h = int(match.group("start_hour"))
                start_min = int(match.group("start_min"))

                meta_time_start = self.normalized_time((start_y, start_m, start_d, start_h, start_min))

                end_y = start_y
                end_m = start_m
                end_d = start_d
                end_h = int(match.group("end_hour"))
                end_min = int(match.group("end_min"))

                meta_time_end = self.normalized_time((end_y, end_m, end_d, end_h, end_min))

            else:
                raise Exception("program time not found: {}".format(time_txt))
                meta_time_start = None
                meta_time_end = None


            meta = ProgramMeta(title=meta_title, cast_name=meta_cast, time_start=meta_time_start, time_end=meta_time_end)


            playbtn_class_name = "live-detail__play"
            #再生するボタンがクリッカブルになるまで待つ
            element = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.CLASS_NAME, playbtn_class_name))
            )
            
            #再生するボタンをクリック
            driver.find_element_by_class_name(playbtn_class_name).click()

            ok_btn = 'a.btn.btn--primary-red.btn--xx-large'
            #確認モーダルのOKが現れるまでまつ
            element2 = WebDriverWait(driver, 10).until(
                    EC.text_to_be_present_in_element((By.CSS_SELECTOR, ok_btn), 'OK')
            )

            #OKボタンを押す
            driver.find_element_by_css_selector(ok_btn).click()

          
            try:
                seekbar_selector = '#seekbar>.bar.active' 
                #再生位置のシークバーのvisibilityをチェックする(widthが0より大きいことをチェック)
                element3 = WebDriverWait(driver, 10).until(
                        EC.visibility_of_element_located((By.CSS_SELECTOR, seekbar_selector))
                )
            except STimeoutException as e:
                time.sleep(5)

            except selenium.common.exceptions.UnexpectedAlertPresentException as e:
                alert = driver.switch_to.alert
                alert.dismiss()
                time.sleep(5)


        finally:
            #再生を止めるため、ブランクページに移動
            driver.get('about:blank')


        return meta

    def get_playlist_info(self, har):
        """harからX-Radiko-AuthTokenを探して返す"""

        token = "" 
        for entry in har['log']['entries']:
            req = entry['request']
            if req["method"] == "GET" and req["url"].startswith("https://radiko.jp/v2/api/ts/playlist.m3u8?"):
                m3u8_url = req["url"]
                for header in req['headers']:
                    if header['name'] == 'X-Radiko-AuthToken':
                        token = header['value']
                        break
                break
        else:
            #tokenが見つからなかった
            pass

        return token, m3u8_url

    def get_proxy(self, file_path):
        """browsermob-proxyのサーバーとプロクシーを返す"""
       
        if self._server:
            server = self._server
        else:
            server = Server(file_path)
            #サーバーを開始して利用可能になるまでまつ
            server.start()

            self._server = server


        if self._proxy:
            proxy = self._proxy
        else:
            proxy = server.create_proxy()
            self._proxy = proxy
        

        return proxy, server

    def get_driver(self, proxy):
        """Firefoxのdriverを返す"""

        if self._driver:
            return self._driver

        ff_option = Options()
        ff_option.add_argument('-headless')

        profile = webdriver.FirefoxProfile()
        profile.set_preference("media.volume_scale", "0.0")
        profile.set_proxy(proxy.selenium_proxy())

        args = {
                "firefox_profile": profile,
                "firefox_options": ff_option
        }

        driver = webdriver.Firefox(**args)
        self._driver = driver

        return self._driver

    def normalized_time(self, t):
        """24時間表記に治す"""
        year = int(t[0])
        month = int(t[1])
        day = int(t[2])
        hour = int(t[3])
        min_ = int(t[4])

        start = datetime(year, month, day)
        
        time_d = timedelta(hours=hour, minutes=min_)

        normalized = start + time_d

        return normalized.timetuple()


    def has_ffmpeg(self):
        """ffmpegがpathにあるか調べる"""
        for p in os.get_exec_path():
            p = Path(p)

            w = p / "ffmpeg.exe"
            u = p / "ffmpeg"
            if w.is_file():
                return True, "ffmpeg.exe"
            
            elif u.is_file():
                return True, "ffmpeg"

        return False, ""


    def get_filename(self, meta):
        """ファイル名を返す"""
        if meta.cast_name:
            cast = " ({cast_name})".format(cast_name=meta.cast_name)
        else:
            cast = ""

        filename = "{title}{cast} - {day}.{ext}".format(title=meta.title, cast=cast, day=time.strftime('%m-%d', meta.time_start), ext=self.extention)

        return re.sub('[/\\:*?"<>|]', '_', filename)



    def __del__(self):
        """後始末"""

        if self._server:
            self._server.stop()

        if self._driver:
            self._driver.quit()

        logs = ["bmp.log","geckodriver.log", "server.log"]
        base = Path('./')
        for f in logs:
            log = base / Path(f)
            if log.is_file():
                log.unlink()


class NoBrowsermobProxyError(Exception):
    """browsermob-proxyが見つからなかった時の例外"""

    def __init__(self, path):
        self.message = "{path}にbrowsermob-proxyが見つかりませんでした".format(path=path)

class NotAURLError(Exception):
    """不完全なurlだった時の例外"""

    def __init__(self, url):
        self.message = "{url}は不完全なURLです".format(url)



def parse_args():
    """引数のパース"""

    options = {}

    parser = argparse.ArgumentParser(description="Radikoの番組を保存")

    #Radikoの視聴URL
    parser.add_argument('urls', nargs='+')

    #browsermobproxyのパス
    parser.add_argument('-p', '--path')

    #codec
    parser.add_argument('-c', '--codec', default='copy')

    #quality
    parser.add_argument('-q', '--quality', default=4, type=int)

    #ext
    parser.add_argument('-e', '--extention', default='m4a')

    #max_workers
    parser.add_argument('-w', '--workers', default=1, type=int)

    #start parse
    args = parser.parse_args()

    options['urls'] = args.urls
    options['codec'] = args.codec
    options['quality'] = args.quality
    options['extention'] = args.extention
    options['max_workers'] = args.workers

    #オプションのbmpのパス
    options['bmp_path'] = args.path

    return options


if __name__ == '__main__':
    options = parse_args()
    radiko = Radikosave(**options)
    radiko.save_files()

