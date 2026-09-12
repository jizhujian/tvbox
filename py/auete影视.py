# -*- coding: utf-8 -*-
import sys
import json
import re
import datetime
import base64
import requests
from bs4 import BeautifulSoup
sys.path.append('..')
from base.spider import Spider


class Spider(Spider):

    def __init__(self):
        super().__init__()
        self.name = "auete影视"
        self.tag = "auete"
        self.tag_name = "auete影视"
        self.siteUrl = "https://www.aeete.com"
        self.classes = [
            {"type_id": "Movie", "type_name": "电影"},
            {"type_id": "Tv", "type_name": "剧集"},
            {"type_id": "Zy", "type_name": "综艺"},
            {"type_id": "Dm", "type_name": "动漫"},
            {"type_id": "qita", "type_name": "其他"}
        ]

    def getName(self):
        return self.name

    def init(self, extend=""):
        print(f"初始化auete影视爬虫, extend={extend}")
        try:
            self.extendDict = json.loads(extend) if extend else {}
        except:
            self.extendDict = {}

    def destroy(self):
        pass

    def getDatatime(self):
        now = datetime.datetime.now()
        gmt_format = '%a %b %d %Y %H:%M:%S GMT+0800 (中国标准时间)'
        dataTime = now.strftime(gmt_format)
        return dataTime

    def cacu(self, code):
        if "=" in code:
            code = code[:code.find("=")]
        elif code[-1] == "2" or code[-1] == "7":
            code = code[:-1]
            if code[-1] == "4" or code[-1] == "-":
                code = code[:-1]
        code = code.replace("I", "1")
        code = code.replace("l", "1")
        if code.isdigit():
            if len(code) > 4:
                code = code[:4]
            return int(code[:2]) - int(code[2:])
        elif "+" in code:
            code = code.split("+")
            return int(code[0]) + int(code[1])
        elif "-" in code:
            code = code.split("-")
            return int(code[0]) - int(code[1])
        elif "x" in code:
            code = code.split("x")
            return int(code[0]) * int(code[1])
        return 0

    def getHeaders(self, url=""):
        headers = {}
        if url:
            headers.setdefault("Referer", url)
        headers.setdefault("Accept", "*/*")
        headers.setdefault("Accept-Encoding", "gzip, deflate, br")
        headers.setdefault("User-Agent",
                           "Mozilla/5.0 (Linux; Android 7.1.1; OPPO R9sk Build/NMF26F; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/70.0.3538.80 Mobile Safari/537.36 alookweb/5.12.3")
        return headers

    def sort_play(self, data):
        for item in data:
            play_from = item.get('vod_play_from', '')
            play_url = item.get('vod_play_url', '')
            from_list = play_from.split('$$$')
            url_list = play_url.split('$$$')
            paired = list(zip(from_list, url_list))
            paired.sort(key=lambda x: x[0])
            sorted_from = '$$$'.join([p[0] for p in paired])
            sorted_url = '$$$'.join([p[1] for p in paired])
            item['vod_play_from'] = sorted_from
            item['vod_play_url'] = sorted_url
        return data

    def verifyCode(self, key):
        retry = 5
        while retry:
            try:
                session = requests.session()
                img = session.get(
                    url=f"{self.siteUrl}/include/vdimgck.php?get={self.getDatatime()}",
                    headers=self.getHeaders()
                ).content
                scode = session.post('https://api.nn.ci/ocr/b64/text', data=base64.b64encode(img).decode()).text
                code = self.cacu(scode)
                Headerck = self.getHeaders()
                new_headers = {
                    "Origin": self.siteUrl,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Upgrade-Insecure-Requests": "1"
                }
                Headerck.update(new_headers)
                cKurl = f"{self.siteUrl}/auete4so.php?scheckAC=check&page=&searchtype=&order=&tid=&area=&year=&letter=&yuyan=&state=&money=&ver=&jq="
                resn = session.post(
                    url=cKurl,
                    data={'validate': code, 'searchword': key},
                    headers=Headerck
                )
                cookie = str(session.cookies).lower()
                if "ok" in cookie:
                    return resn
            except Exception as e:
                print(f"验证码验证失败: {e}")
                if e.__class__.__name__ == 'ConnectTimeout':
                    break
            finally:
                retry = retry - 1
        return None

    def homeContent(self, filter):
        result = {"class": self.classes}
        result['filters'] = self.config.get('filter', {}) if filter else {}
        return result

    def homeVideoContent(self):
        try:
            rsp = requests.get(url=self.siteUrl, headers=self.getHeaders(), timeout=10)
            rsp.encoding = 'utf-8'
            root = BeautifulSoup(rsp.text, "html.parser")
            items = root.select("ul.threadlist > li")
            videos = []
            for item in items:
                try:
                    img = item.select_one("img")
                    name = img.get("title", "")
                    pic = img.get("src", "")
                    pic_match = re.search(r'http*(\S+)', pic)
                    if pic_match:
                        pic = pic_match.group()
                    mark_tag = item.select_one(".hdtag")
                    mark_text = self.tag_name + " " + (mark_tag.get_text() if mark_tag else "")
                    a_tag = item.select_one("a")
                    sid = a_tag.get("href", "")
                    sid = self.tag + "$" + sid
                    videos.append({
                        "vod_id": sid,
                        "vod_name": name,
                        "vod_pic": pic,
                        "vod_remarks": mark_text
                    })
                except Exception as e:
                    continue
            return {"list": videos}
        except Exception as e:
            print(f"[auete影视] 获取首页视频失败: {e}")
            return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = int(pg) if pg else 1
            if extend is None:
                extend = {}
            if isinstance(extend, str):
                try:
                    extend = json.loads(extend)
                except:
                    extend = {}
            subtype_tag = extend.get("class", "")
            if page == 1:
                page_str = "index"
            else:
                page_str = "index" + str(page)
            url = f"{self.siteUrl}/{tid}{subtype_tag}/{page_str}.html"
            rsp = requests.get(url=url, headers=self.getHeaders(), timeout=10)
            rsp.encoding = 'utf-8'
            root = BeautifulSoup(rsp.text, "html.parser")
            items = root.select("ul.threadlist > li")
            videos = []
            for item in items:
                try:
                    img = item.select_one("img")
                    name = img.get("title", "")
                    pic = img.get("src", "")
                    pic_match = re.search(r'http*(\S+)', pic)
                    if pic_match:
                        pic = pic_match.group()
                    mark_tag = item.select_one(".hdtag")
                    mark_text = self.tag_name + " " + (mark_tag.get_text() if mark_tag else "")
                    a_tag = item.select_one("a")
                    sid = a_tag.get("href", "")
                    sid = self.tag + "$" + sid
                    videos.append({
                        "vod_id": sid,
                        "vod_name": name,
                        "vod_pic": pic,
                        "vod_remarks": mark_text
                    })
                except Exception as e:
                    continue
            return {
                "list": videos,
                "page": page,
                "pagecount": 999,
                "limit": 24,
                "total": 999999
            }
        except Exception as e:
            print(f"[auete影视] 获取分类内容失败: {e}")
            return {
                "list": [],
                "page": int(pg) if pg else 1,
                "pagecount": 0,
                "limit": 0,
                "total": 0
            }

    def searchContent(self, key, quick, pg):
        try:
            resn = self.verifyCode(key)
            resn.encoding = 'utf-8'
            root = BeautifulSoup(resn.text, "html.parser")
            items = root.select("ul.threadlist > li")
            videos = []
            for item in items:
                try:
                    img = item.select_one("img")
                    name = img.get("alt", "")
                    if key not in name:
                        continue
                    mark_tag = item.select_one(".hdtag")
                    mark_text = self.tag_name + " " + (mark_tag.get_text() if mark_tag else "")
                    pic = img.get("src", "")
                    a_tag = item.select_one("a")
                    sid = a_tag.get("href", "")
                    sid = self.tag + "$" + sid
                    videos.append({
                        "vod_id": sid,
                        "vod_name": name,
                        "vod_pic": pic,
                        "vod_remarks": mark_text
                    })
                except Exception as e:
                    continue
            return {
                "list": videos,
                "page": int(pg) if pg else 1,
                "pagecount": 999,
                "total": len(videos)
            }
        except Exception as e:
            print(f"[auete影视] 搜索失败: {e}")
            return {
                "list": [],
                "page": int(pg) if pg else 1,
                "pagecount": 0,
                "total": 0
            }

    def detailContent(self, ids):
        try:
            vid = ids[0].split("$")[-1]
            url = f"{self.siteUrl}/{vid}"
            rsp = requests.get(url=url, headers=self.getHeaders(), timeout=10)
            rsp.encoding = 'utf-8'
            root = BeautifulSoup(rsp.text, "html.parser")
            node = root.select_one("div.detail-poster")
            title_tag = node.select_one("img")["alt"]
            img_tag = node.select_one("img")["src"]
            vod = {
                "vod_id": self.tag + "$" + vid,
                "vod_name": title_tag,
                "vod_pic": img_tag,
                "type_name": "",
                "vod_year": "",
                "vod_area": "",
                "vod_remarks": "",
                "vod_actor": "",
                "vod_director": "",
                "vod_content": ""
            }
            info_paragraphs = root.select("div.message.break-all > p")
            if info_paragraphs and len(info_paragraphs) > 0:
                vod['vod_content'] = info_paragraphs[-1].get_text()
            for p in info_paragraphs:
                content = p.get_text()
                content = ''.join(content.split()).replace("/", "")
                if "分类" in content:
                    vod['type_name'] = content.replace("◎影片分类", "").replace("：", "").replace(":", "")
                elif "备注" in content:
                    vod['vod_remarks'] = content.replace("◎影片备注", "").replace("：", "").replace(":", "")
                elif "地区" in content:
                    vod['vod_area'] = content.replace("◎影片地区", "").replace("：", "").replace(":", "")
                elif "主演" in content:
                    vod['vod_actor'] = content.replace("◎影片主演", "").replace("：", "").replace(":", "")
                elif "导演" in content:
                    vod['vod_director'] = content.replace("◎影片导演", "").replace("：", "").replace(":", "")
            play_from_list = []
            play_headers = root.select("div.card-header>span")
            for v in play_headers:
                i_tag = v.find("i", class_="fa-play-circle")
                if i_tag:
                    b_tag = i_tag.find_next_sibling("b")
                    if b_tag:
                        p = b_tag.get_text(strip=True).replace("『", "").replace("』", "").replace(title_tag, "")
                        play_from_list.append(p)
            vod['vod_play_from'] = "$$$".join(play_from_list) if play_from_list else ""
            play_url_list = []
            ul_list = root.select("ul.episode-list")
            for ul in ul_list:
                play_items = []
                a_list = ul.select("li")
                for a_tag in a_list:
                    name = a_tag.select_one("a").get("title", "")
                    href = a_tag.select_one("a").get("href", "")
                    tid_match = re.search(r'(\S+).html', href)
                    if tid_match:
                        play_items.append(name + "$" + self.tag + "___" + tid_match.group(1))
                if play_items:
                    play_url_list.append("#".join(play_items))
            vod['vod_play_url'] = "$$$".join(play_url_list) if play_url_list else ""
            sorted_data = self.sort_play([vod])
            return {"list": sorted_data}
        except Exception as e:
            print(f"[auete影视] 获取详情失败: {e}")
            return {"list": []}

    def playerContent(self, flag, id, vipFlags):
        try:
            vid = id.split("___")[-1]
            url = f"{self.siteUrl}{vid}.html"
            rsp = requests.get(url=url, headers=self.getHeaders(), timeout=10)
            rsp.encoding = 'utf-8'
            root = BeautifulSoup(rsp.text, "html.parser")
            scripts = root.select("script")
            originUrl = ""
            pn = ""
            for script in scripts:
                content = script.get_text()
                if "vfrom" in content:
                    parts = re.split(';', content)
                    if len(parts) >= 4:
                        originUrl_match = re.search(r'"(.*?)"', parts[3])
                        if originUrl_match:
                            originUrl = base64.b64decode(originUrl_match.group(1)).decode("utf-8")
                    if len(parts) >= 5:
                        pn_match = re.search(r'"(.*?)"', parts[4])
                        if pn_match:
                            pn = pn_match.group(1)
                    break
            if "http" in originUrl:
                return {
                    "header": self.getHeaders(),
                    "parse": 0,
                    "playUrl": "",
                    "url": originUrl
                }
            else:
                if pn:
                    playphrase = requests.get(url=f"{self.siteUrl}/js/player/{pn}.html", headers=self.getHeaders(),
                                              timeout=10)
                    playphrase.encoding = 'utf-8'
                    phrase_match = re.search(r'src="([^"]*)"', playphrase.text)
                    if phrase_match:
                        phraseUrl = phrase_match.group(1).split("'")[0]
                        if "http" not in phraseUrl:
                            phraseUrl = self.siteUrl + phraseUrl
                        header = self.getHeaders()
                        header.update({
                            "User-Agent": "Mozilla/5.0 (Linux; U;Android 7.1.1; OPPO R9sk Build/NMF26F; wv) Version/4.0 Chrome/100.0.4896.58 Quark/6.10.5.520 Mobile Safari/537.36"
                        })
                        return {
                            "header": header,
                            "parse": 1,
                            "playUrl": phraseUrl,
                            "url": originUrl
                        }
            return {"parse": 0, "playUrl": "", "url": "", "header": {}}
        except Exception as e:
            print(f"[auete影视] 获取播放器失败: {e}")
            return {"parse": 0, "playUrl": "", "url": "", "header": {}}

    def localProxy(self, param):
        pass

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    # ========== 配置 ==========
    config = {
        "player": {},
        "filter": {
            "Movie": [
                {
                    "key": "class",
                    "name": "剧情",
                    "value": [
                        {"n": "全部", "v": ""},
                        {"n": "喜剧片", "v": "/xjp"},
                        {"n": "动作片", "v": "/dzp"},
                        {"n": "爱情片", "v": "/aqp"},
                        {"n": "科幻片", "v": "/khp"},
                        {"n": "恐怖片", "v": "/kbp"},
                        {"n": "惊悚片", "v": "/jsp"},
                        {"n": "战争片", "v": "/zzp"},
                        {"n": "剧情片", "v": "/jqp"}
                    ]
                }
            ],
            "Tv": [
                {
                    "key": "class",
                    "name": "剧情",
                    "value": [
                        {"n": "全部", "v": ""},
                        {"n": "美剧", "v": "/oumei"},
                        {"n": "韩剧", "v": "/hanju"},
                        {"n": "日剧", "v": "/riju"},
                        {"n": "泰剧", "v": "/yataiju"},
                        {"n": "网剧", "v": "/wangju"},
                        {"n": "台剧", "v": "/taiju"},
                        {"n": "国产", "v": "/neidi"},
                        {"n": "港剧", "v": "/tvbgj"},
                        {"n": "英剧", "v": "/yingju"}
                    ]
                }
            ],
            "Zy": [
                {
                    "key": "class",
                    "name": "剧情",
                    "value": [
                        {"n": "全部", "v": ""},
                        {"n": "国综", "v": "/guozong"},
                        {"n": "韩综", "v": "/hanzong"},
                        {"n": "美综", "v": "/meizong"}
                    ]
                }
            ],
            "Dm": [
                {
                    "key": "class",
                    "name": "剧情",
                    "value": [
                        {"n": "全部", "v": ""},
                        {"n": "动画", "v": "/donghua"},
                        {"n": "日漫", "v": "/riman"},
                        {"n": "国漫", "v": "/guoman"},
                        {"n": "美漫", "v": "/meiman"}
                    ]
                }
            ],
            "qita": [
                {
                    "key": "class",
                    "name": "剧情",
                    "value": [
                        {"n": "全部", "v": ""},
                        {"n": "记录片", "v": "/Jlp"},
                        {"n": "经典片", "v": "/Jdp"},
                        {"n": "经典剧", "v": "/Jdj"},
                        {"n": "网大电影", "v": "/wlp"},
                        {"n": "国产老电影", "v": "/laodianying"}
                    ]
                }
            ]
        }
    }
