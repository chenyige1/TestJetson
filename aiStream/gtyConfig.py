import configparser
import re
import uuid
from getmac import get_mac_address
from colorama import Fore

newLine = re.compile(r'\\n')


# 获取本机的mac地址，用于加密
# pip install getmac
def getMacAddress():
    # mac = get_mac_address(interface='eth0')
    mac = get_mac_address(interface='enP8p1s0')
    return mac.upper()

def getMachineId():
    mac = getMacAddress()
    machineId = macList[mac]
    # print(__file__,"machineId",machineId)
    return machineId



#每个设备有一个有线网卡和一个wifi网卡，所以都需要指定。
# 获得wifi网卡mac的方法：打开wifi，关闭有线网络
# 获得有线网卡mac的方法：打开有线网络，关闭wifi
macList = {
    "48:8F:4C:DF:05:B4":"T001",
    "3C:6D:66:03:7F:B1":"T001",
    "3C:6D:66:11:83:A1":"T003",
    "3C:6D:66:11:84:93":"T004",
    "3C:6D:66:11:84:6D":"T005",
    "3C:6D:66:0D:5D:21":"T006",
    "3C:6D:66:11:84:8E":"T007",
    "3C:6D:66:11:83:90":"T008",
    "3C:6D:66:11:83:8E":"T009",
    "3C:6D:66:11:84:5F":"T010",
    "3C:6D:66:1F:5E:3D":"T011",
}


# 重载配置接口类，解决：1. 不区分大小写，2. 写入时配置文件中的注释丢失
class gtyConfigParser(configparser.ConfigParser):
    def __init__(self, defaults=None, dict_type=dict, allow_no_value=True):
        configparser.ConfigParser.__init__(self, defaults, dict_type, allow_no_value)

    def optionxform(self, optionStr):
        return optionStr


class ConfigFileHandler:

    def __init__(self, fileName='./config.ini'):
        mac = getMacAddress()
        if mac in macList.keys():
            self.config = gtyConfigParser()
            self.configFileName = fileName
            self.data = None
            self.openConfigFile(fileName)
            self.saftyCheck = True

            self.dropFirstCharNum=self.read("bib","dropFirstCharNum","int",0)
            self.digitNum = self.read("bib","digitNum","int",4)
            self.letterSet = self.read("bib","letterSet","string","")


            self.saveRunnerImageEverySecond =  self.read("IO","saveRunnerImageEverySecond","float",0)
            self.padSize =  self.read("IO","imagePadSize","int","100")
            self.imageSaveEntireFrame = self.read("IO","imageSaveEntireFrame","int",0)

            self.faceBlurEnable = self.read("ai","faceBlurEnable","int",1)

            self.showBib = self.read("display","showBib","int",0)
            if self.showBib>0:
                self.saveBib = 0.7

            self.language = self.read("language","language","string","english")
            self.pic_name = self.read("test_state","pic_name_change","bool",0)

        else:
            print(Fore.RED+"================================")
            print("safty check failed")
            print("================================"+Fore.RESET)
            self.config = None
            self.configFileName = None
            self.data = None
            self.saftyCheck = False

    # 打开配置文件，检查
    def openConfigFile(self, fileName='./config.ini'):
        if fileName is None:
            fileName = self.configFileName
        try:
            self.config.read(fileName, encoding="utf-8")
        except Exception as e:
            print(e)

    # 读取数据
    def read(self, section, option, returnType="string", defaultValue=None):
        if defaultValue is None:
            if returnType == "string":
                defaultValue = ""
            if returnType == "int" or returnType == "float":
                defaultValue = 0
            if returnType == "bool":
                defaultValue = False
        try:
            if returnType == "string":
                s = self.config.get(section, option)
                if s == "":
                    return defaultValue
                return newLine.sub('\n', s)
            if returnType == "int":
                s = self.config.get(section, option)
                if s == "":
                    return defaultValue
                return int(s)
            if returnType == "float":
                s = self.config.get(section, option)
                if s == "":
                    return defaultValue
                return float(s)
            if returnType == "bool":
                s = self.config.get(section, option)
                if s in ['0', '']:
                    return False
                else:
                    return True

        except Exception as e:
            print(e)
            return defaultValue


# 一个配置文件实例
# configTry = ConfigFileHandler("../config.ini")
config = ConfigFileHandler()

import os
import datetime


dateTimeString = str(datetime.datetime.now().strftime("%Y-%m-%dT%Hh%Mm%Ss"))
outputFolder = './output/run_' + dateTimeString
imageSavePath = outputFolder + "/images/"
os.makedirs(imageSavePath)















