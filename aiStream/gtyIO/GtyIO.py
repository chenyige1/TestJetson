import datetime
import os
import random
import threading
import time
import traceback
import urllib
import urllib.request
from multiprocessing import Process, Queue, Lock

import cv2
import numpy as np
from pip._vendor import requests

import gtyConfig
from gtyStream.gtyStreamUtils import loadSourceConfig
from . import ioTools, OssHandler
import params
import json
from colorama import Fore

import gtyLog


class GtyIO:
    def __init__(self, eventQ):
        self.lock = Lock()
        self.configHandler = gtyConfig.ConfigFileHandler()
        if not self.configHandler.saftyCheck:
            return
        self.number_sources = self.loadsource()

        self.eventId = self.configHandler.read("event", "eventId", "string", "exampleEventId")
        self.eventQ = eventQ

        self.testImage = np.zeros((100, 100, 4), dtype=np.float32)

        self.eventEngine = threading.Thread(target=self.eventEngine)
        self.eventEngine.start()

        self.imageSaveFileNameCounter = 0

        self.outputFolder = gtyConfig.outputFolder
        self.saveFileName = gtyConfig.outputFolder + "/" + datetime.datetime.now().strftime(
            "%Y-%m-%dT%Hh%Mm%Ss") + ".csv"
        self.imageSavePath = gtyConfig.imageSavePath

        # 准备存储的运动员缓冲区，是一个字典。键为运动员的随机ID，值为一个列表。
        # 列表中每一个元素代表一张照片，元素结构是一个字典{fileName:_,image:_}
        self.imageCache = {}

        # 运动员数据的缓冲区,是一个字典。键为运动员的随机ID，值为一个列表。
        # 列表中每一个元素代表一条运动员数据
        self.runnerDataCache = {}

        #向stream传递记录地址
        self.sendEvent("STREAM", "outputPath", self.outputFolder)

        # 待上传的runner数据
        self.data2Web = []
        self.data2WebTemp = []
        self.data2ServerNum = 0
        # 向备用服务器上传
        self.data2WebBack = []
        self.data2WebBackTemp = []
        self.data2ServerBackNum = 0

        # oss上传对象
        self.oss = OssHandler.OssHandler(self.eventQ)

        # oss上传主进程
        t = Process(target=self.oss.uploadImagesParallel, args=(self.imageSavePath, True))
        t.start()

        # 对于磁盘可用空间进行监控，如果小于指定值则删除一些数据
        # print("self.outputFolder", self.outputFolder)
        t = Process(target=ioTools.removeRunFilesWhenDiskFull, args=(self.outputFolder,self.number_sources))
        t.start()

        self.imageCounter = 0
        self.dataCounter = 0
        #运动员总数
        self.runnerNum = 0
        #识别出号码的运动员总数
        self.runnerBibNum = 0

    def loadsource(self):
        sourceUrls, frameWidth, frameHeight = loadSourceConfig(self.configHandler)
        number_sources = 0
        for s in sourceUrls:
            if s is not None:
                number_sources += 1
        return number_sources

    def work(self):
        localCounter = 0
        while True:
            localCounter += 1
            if localCounter % 20 == 0:
                # 把数据通过web请求发送到服务器
                self.sendEvent("IO", "web_uploadDataToServer")
                gtyLog.logger.debug("==========gtyIO worker", printOutput=False)
            time.sleep(0.1)

    def eventEngine(self):
        while True:
            time.sleep(0.001)

            if 'IO' not in self.eventQ.keys():
                continue

            if not self.eventQ['IO'].empty():  # 事件队列非空
                try:
                    event = self.eventQ['IO'].get(block=True, timeout=1)  # 获取队列中的事件 超时1秒
                    self.handleEventResult(event)
                except Exception as e:
                    gtyLog.logger.error(__file__, 'eventEngine error', {e})
            else:
                pass

    def sendEvent(self, task, eventName, eventData=None):
        if eventData is None:
            eventData = []
        e = [eventName, eventData]
        try:
            with self.lock:
                if task.upper() in self.eventQ.keys():
                    self.eventQ[task.upper()].put(e)
        except Exception as e:
            gtyLog.logger.error("io send data error", __file__, e)

    def handleEventResult(self, event):
        task = event[0]
        data = event[1]
        # 定时存储图片
        if task == 'io_saveImage':
            imageStr = data[0]
            image = data[1]
            image = cv2.cvtColor(image, cv2.COLOR_RGBA2BGRA)
            fileName = self.imageSavePath + "runner_" + imageStr + ".jpg"
            cv2.imwrite(fileName, image)
            self.imageSaveFileNameCounter += 1
            return
        # 缓存一张图片，等待将来存储
        if task == 'io_cacheImage':
            randomId = data[0]
            imageStr = data[1]
            image = cv2.cvtColor(data[2], cv2.COLOR_RGBA2BGRA)
            # 把图片调整为16/9
            if gtyConfig.config.imageSaveEntireFrame == 0:
                image = ioTools.resizeToRatio(image, 16.0 / 9.0)
                # 指定缩放到同一尺寸
                h, w = image.shape[:2]
                if w > 400:
                    image = cv2.resize(image, (400, 711))
            if randomId not in self.imageCache:
                self.imageCache[randomId] = []
            self.imageCache[randomId].append(
                {"fileName": self.imageSavePath + "runner_" + imageStr + ".jpg", "image": image})
            return
        if task == 'io_cacheRunnerData':
            # runner.id, runner.randomId, runner.bibStr, "created time string",runner.createdTimeStr,
            # fileName, gender, cam, frame
            randomId = data[1]
            if randomId not in self.runnerDataCache:
                self.runnerDataCache[randomId] = []
            self.runnerDataCache[randomId].append(data)
            return
        # 运动员被删除出画面时向IO进程发送最终的号码布，并通知存储图片
        if task == "io_dropRunner":
            bibStr = data[1]
            gender = data[2]
            self.runnerNum += 1
            if bibStr == "":
                bibStr = "NOBIB"
            if bibStr != "NOBIB":
                self.runnerBibNum += 1
            # print(datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            gtyLog.logger.info(Fore.CYAN + "recognition index: %.2f" % (
                        float(self.runnerBibNum) / self.runnerNum * 100) +  Fore.RESET)
            # 存储图片
            for img in self.imageCache[data[0]]:
                cv2.imwrite(img["fileName"].replace("NOBIB", bibStr).replace("GENDER",gender), img["image"])
                self.imageCounter += 1
            self.imageCache.pop(data[0])
            # 发送数据 data[0]是io_cacheRunnerData的randomId
            for runner in self.runnerDataCache[data[0]]:
                runner[2] = bibStr
                runner[5] = runner[5].replace("NOBIB", bibStr).replace("GENDER",gender)
                runner[6] = gender
                self.data2Web.append(runner)
                self.data2WebBack.append(runner)
                # 将图片数据写入csv中
                ioTools.recordEpcDefaultFormat(self.saveFileName, runner)
                self.dataCounter += 1
            self.runnerDataCache.pop(data[0])
            if self.dataCounter != self.imageCounter:
                gtyLog.logger.info(__file__, self.imageCounter, self.dataCounter)
            return

        if task == 'web_uploadDataToServer':
            self.uploadDataToServer()
            return
        if task == 'io_uploadToServerSuccess':
            self.uploadDataToServerSuccess(data[0])
            return

    def uploadDataToServer(self):
        # 向主服务器上传
        gtyLog.logger.info(Fore.LIGHTGREEN_EX + "uploaded to server:", self.data2ServerNum, "uploaded to server back:",
                           self.data2ServerBackNum, Fore.RESET)
        if len(self.data2WebTemp) == 0:
            self.data2WebTemp = self.data2Web[0:min(len(self.data2Web), 50)]
        t = Process(target=self.uploadDataToServerPost, args=(self.data2WebTemp, 0))
        t.start()
        # 向备用服务器上传
        if len(self.data2WebBackTemp) == 0:
            self.data2WebBackTemp = self.data2WebBack[0:min(len(self.data2WebBack), 50)]
        t = Process(target=self.uploadDataToServerPost, args=(self.data2WebBackTemp, 1))
        t.start()

    def uploadDataToServerSuccess(self, back):
        if back == 0:
            # 主服务器收到
            self.data2Web = self.data2Web[len(self.data2WebTemp):]
            self.data2ServerNum += len(self.data2WebTemp)
            self.data2WebTemp = []
        if back == 1:
            # 备用服务器收到
            self.data2WebBack = self.data2WebBack[len(self.data2WebBackTemp):]
            self.data2ServerBackNum += len(self.data2WebBackTemp)
            self.data2WebBackTemp = []

    '''
    =======================================================================================================================
    此类中的具体的工作函数
    =======================================================================================================================
    '''


    def uploadDataToServerPost(self,runnerList,back=0):
        if len(runnerList) == 0:
            return
        try:
            md5String = "gty"
            if md5String is None:
                md5String = ""
            token = str(random.randint(10000000, 99999999))

            serverLocation = ""
            if back == 0:
                serverLocation = params.webServerLocation
            elif back == 1:
                serverLocation = params.webServerLocationBack

            url = serverLocation

            data = {}
            data["machineId"] = gtyConfig.getMachineId()
            data["eventId"] = self.eventId
            data["runnerNum"] = len(runnerList)
            runners = []
            for runner in runnerList:
                runners.append({
                    "runnerId": runner[0],
                    "randomId": runner[1],
                    "bib": runner[2],
                    "info": runner[3],
                    "timeString": runner[4],
                    "picName": "runner_"+runner[5]+'.jpg',
                    "gender":runner[6]
                })
            data["runners"] = runners
            data["t"] = str(token)
            data["sign"] = ioTools.get_token(token, md5String)
            # print(url,data)
            try:
                res = requests.post(url, json=data)
                if res.status_code != 200:
                    return
            except Exception as e:
                gtyLog.logger.error(e,printOutput=False)
                return

            getData = res.text
            try:
                # print("====================getData",getData)
                res = json.loads(getData)
                # print(serverLocation,getData)
                gtyLog.logger.info(getData, printOutput=False)
                if 'ok' == res["code"]:
                    self.sendEvent('IO', 'io_uploadToServerSuccess', [back])
            except Exception as e:
                gtyLog.logger.error(serverLocation, getData)
                gtyLog.logger.error("upload error to server ", back, ": ", e)
        except Exception as e:
            gtyLog.logger.error("web upload failed:", e)
        pass

def main(eventQ):
    gtyLog.logger.info("\n===================IO task started===================")
    try:
        io = GtyIO(eventQ)
        # io.work()
    except Exception as e:
        traceback.extract_stack()
        gtyLog.logger.error(e, traceback.format_exc())
