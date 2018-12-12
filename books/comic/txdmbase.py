#!/usr/bin/env python
# -*- coding:utf-8 -*-
import datetime
from bs4 import BeautifulSoup
from config import TIMEZONE
from lib.urlopener import URLOpener
from lib.autodecoder import AutoDecoder
from books.base import BaseComicBook
from apps.dbModels import LastDelivered
import re
import base64
import json

class txdmbase(BaseComicBook):
    title               = u''
    description         = u''
    language            = ''
    feed_encoding       = ''
    page_encoding       = ''
    mastheadfile        = ''
    coverfile           = ''
    host                = 'http://ac.qq.com/'
    feeds               = [] #子类填充此列表[('name', mainurl),...]
    def eval(self,cmd):
        return "%s"%(int(eval(cmd)))
    #使用此函数返回漫画图片列表[(section, title, url, desc),...]
    def ParseFeedUrls(self):
        urls = [] #用于返回
        
        newComicUrls = self.GetNewComic() #返回[(title, num, url),...]
        if not newComicUrls:
            return []
        
        decoder = AutoDecoder(isfeed=False)
        for title, num, url in newComicUrls:
            default_log.info('Trying to fetch #%d'%num)
            opener = URLOpener(self.host, timeout=60)
            result = opener.open(url)
            if result.status_code != 200 or not result.content:
                self.log.warn('fetch comic page failed: %s' % url)
                continue
                
            content = result.content
            base64data = re.findall(r"DATA\s*=\s*'(.+?)'", content)[0]
            nonce = re.findall(r'(window\["[^;]*)',content)[0]
            
            nonce = ''.join(nonce.split('=')[1:])
            nonce = nonce.replace('.toString()','').replace('Math.','').replace('~~','').replace('(+eval','(self.eval')
            nonce = re.sub(r"'([^']+)'\.substring\(([^()]+)\)",r"int('\1'[\2:])",nonce)
            nonce = re.sub(r"'([^']+)'\.charCodeAt\(\)",r"ord('\1')",nonce)
            nonce = re.sub(r"!!!([\d\.]+)",r"int(not not not(\1))",nonce)
            nonce = re.sub(r"!!([\d\.]+)",r"int(not not(\1))",nonce)
            nonce = re.sub(r"!([\d\.]+)",r"int(not(\1))",nonce)
            nonce = re.sub(r"\"([^(]+)\?(.+):([^)]+)\"",r"\2 if \1 else \3",nonce)
            nonce = re.sub(r"parseInt",r"int",nonce)
            nonce = nonce.replace("!!document.getElementsByTagName('html')","1")
            nonce = eval(nonce)
            nonce=re.findall(r'\d+[a-zA-Z]+',nonce)[::-1]
            for i in nonce:
                locate = int(re.sub(r'[a-zA-Z]+','',i))&255
                str = re.sub(r'\d+','',i)
                base64data = base64data[:locate]+base64data[(locate+len(str)):]
            imgjson = json.loads(base64.b64decode(base64data))
            k_page = 0
            for img_url in imgjson.get('picture'):
                k_page += 1
                urls.append((title, k_page, img_url['url'], None)) 
            self.UpdateLastDelivered(title, num)
            
        return urls
    
    #更新已经推送的卷序号到数据库，保留
    def UpdateLastDelivered(self, title, num):
        userName = self.UserName()
        dbItem = LastDelivered.all().filter('username = ', userName).filter('bookname = ', title).get()
        self.last_delivered_volume = u' 第%d话' % num
        if dbItem:
            dbItem.num = num
            dbItem.record = self.last_delivered_volume
            dbItem.datetime = datetime.datetime.utcnow() + datetime.timedelta(hours=TIMEZONE)
        else:
            dbItem = LastDelivered(username=userName, bookname=title, num=num, record=self.last_delivered_volume,
                datetime=datetime.datetime.utcnow() + datetime.timedelta(hours=TIMEZONE))
        dbItem.put()
        
    #根据已经保存的记录查看连载是否有新的章节，返回章节URL列表
    #返回：[(title, num, url),...]，修改
    def GetNewComic(self):
        urls = []    
        if not self.feeds:
            return []
        
        userName = self.UserName()
        decoder = AutoDecoder(isfeed=False)
        for item in self.feeds:
            title, url = item[0], item[1]
            lastCount = LastDelivered.all().filter('username = ', userName).filter("bookname = ", title).get()
            if not lastCount:
                default_log.info('These is no log in db LastDelivered for name: %s, set to 0' % title)
                oldNum = 0
            else:
                oldNum = lastCount.num
                
            opener = URLOpener(self.host, timeout=60)
            result = opener.open(url)
            if result.status_code != 200:
                self.log.warn('fetch index page for %s failed[%s] : %s' % (title, URLOpener.CodeMap(result.status_code), url))
                continue
            content = result.content
            content = self.AutoDecodeContent(content, decoder, self.feed_encoding, opener.realurl, result.headers)
            newestHua = re.findall(ur'最新话：.+?cid/(\d+)">\[',content)
            if newestHua:
                num = int(newestHua[0])
                if num > oldNum:
                    num = oldNum + 1
                    comic_id = re.findall(r'id/(\d+)',url)[0]
                    urls.append((title, num, 'http://ac.qq.com/ComicView/index/id/{0}/cid/{1}'.format(comic_id, num)))
        return urls

