import sys
import threading
import time

import pyds
from gi.repository import GObject, Gst, GLib
import gtyConfig


def cb_newpad(decodebin, decoder_src_pad, data):
    caps = decoder_src_pad.get_current_caps()
    if not caps:
        caps = decoder_src_pad.query_caps()
    gststruct = caps.get_structure(0)
    gstname = gststruct.get_name()
    source_bin = data
    features = caps.get_features(0)

    # Need to check if the pad created by the decodebin is for video and not
    # audio.
    if (gstname.find("video") != -1):
        # Link the decodebin pad only if decodebin has picked nvidia
        # decoder plugin nvdec_*. We do this by checking if the pad caps contain
        # NVMM memory features.
        if features.contains("memory:NVMM"):
            # Get the source bin ghost pad
            bin_ghost_pad = source_bin.get_static_pad("src")
            if not bin_ghost_pad.set_target(decoder_src_pad):
                sys.stderr.write("Failed to link decoder src pad to source bin ghost pad\n")
        else:
            sys.stderr.write(" Error: Decodebin did not pick nvidia decoder plugin.\n")


def decodebin_child_added(child_proxy, Object, name, user_data):
    if (name.find("decodebin") != -1):
        Object.connect("child-added", decodebin_child_added, user_data)

    if "source" in name:
        source_element = child_proxy.get_by_name("source")
        if source_element.find_property('drop-on-latency') != None:
            Object.set_property("drop-on-latency", True)


def create_source_bin(index, Gst, uri, outputPath):
    # Create a source GstBin to abstract this bin's content from the rest of the
    # pipeline
    bin_name = "source-bin-%02d" % index
    nbin = Gst.Bin.new(bin_name)
    if not nbin:
        sys.stderr.write(" Unable to create source bin \n")

    # Source element for reading from the uri.
    # We will use decodebin and let it figure out the container format of the
    # stream and the codec and plug the appropriate demux and decode plugins.
    # uri_decode_bin=Gst.ElementFactory.make("uridecodebin", "uri-decode-bin")
    uri_decode_bin = Gst.ElementFactory.make("nvurisrcbin", "uri-decode-bin")
    if not uri_decode_bin:
        sys.stderr.write(" Unable to create uri decode bin \n")
    # We set the input uri to the source element
    uri_decode_bin.set_property("uri", uri)
    # 自动重连,数字是间隔秒数
    uri_decode_bin.set_property("rtsp-reconnect-interval", 5)
    uri_decode_bin.set_property("rtsp-reconnect-attempts", 50)
    uri_decode_bin.set_property("latency", 150)
    uri_decode_bin.set_property("num-extra-surfaces", 2)
    uri_decode_bin.set_property("gpu-id", 0)
    uri_decode_bin.set_property("smart-rec-cache", 2)
    uri_decode_bin.set_property("cudadec-memtype", 2) #cuda解码缓冲器内存类型为统一

    # smart record
    if gtyConfig.config.pic_name:
        pass
    else:
        uri_decode_bin.set_property("smart-record", 2)
        uri_decode_bin.set_property("smart-rec-dir-path", outputPath)
        uri_decode_bin.set_property("smart-rec-file-prefix", "original_")
        # 如果自动停止后立即开始录制，那么会导致不能正常录制。

        uri_decode_bin.set_property("smart-rec-default-duration", 119)
    # 每个通道间隔2秒，防止出现录像有间隔导致有部分录像不能被完整记录
    t = threading.Timer(10+index*2, action, args=[uri_decode_bin])
    t.start()

    # Connect to the "pad-added" signal of the decodebin which generates a
    # callback once a new pad for raw data has beed created by the decodebin
    uri_decode_bin.connect("pad-added", cb_newpad, nbin)
    uri_decode_bin.connect("child-added", decodebin_child_added, nbin)

    # We need to create a ghost pad for the source bin which will act as a proxy
    # for the video decoder src pad. The ghost pad will not have a target right
    # now. Once the decode bin creates the video decoder and generates the
    # cb_newpad callback, we will set the ghost pad target to the video decoder
    # src pad.
    Gst.Bin.add(nbin, uri_decode_bin)
    bin_pad = nbin.add_pad(Gst.GhostPad.new_no_target("src", Gst.PadDirection.SRC))
    if not bin_pad:
        sys.stderr.write(" Failed to add ghost pad in source bin \n")
        return None
    return nbin, uri_decode_bin


def action(ele):
    a = pyds.alloc_buffer1(4)
    ele.emit('start-sr', a, 2, 600, None)
    # 连续录制，每段2分钟
    t = threading.Timer(120, action, args=[ele])
    t.start()

    # ele.emit('stop-sr', 0)


class Transformer:

    def __init__(self, sourceWidth, sourceHeight, tiledWidth, tiledHeight):
        self.sourceWidth = sourceWidth
        self.sourceHeight = sourceHeight
        self.tiledWidth = tiledWidth
        self.tiledHeight = tiledHeight
        self.wRatio = self.tiledWidth / self.sourceWidth
        self.hRatio = self.tiledHeight / self.sourceHeight

    # 一个坐标点位从源视频空间转换到tiled显示空间
    def ps2d(self, x, y, row, col):
        xd = int(x * self.wRatio + self.tiledWidth * (col - 1))
        yd = int(y * self.hRatio + self.tiledHeight * (row - 1))
        return xd, yd

    # 一个尺寸从源视频空间转换到tiled显示空间
    def ss2d(self, x, y):
        xd = int(x * self.wRatio)
        yd = int(y * self.hRatio)
        return xd, yd

    # 根据点的坐标，判断一个点是哪个sourceId
    def getSourceId(self, x, y):
        if x < self.tiledWidth and y < self.tiledHeight:
            return 0
        if x < self.tiledWidth and y >= self.tiledHeight:
            return 2
        if x >= self.tiledWidth and y < self.tiledHeight:
            return 1
        if x >= self.tiledWidth and y >= self.tiledHeight:
            return 3
        return 0


def loadSourceConfig(configHandler):
    sourceUrls = [None, None, None, None]
    frameWidth = 1920
    frameHeight = 1080
    if configHandler.read("source1", "enable") == "1":
        if configHandler.read("source1", "useExampleMp4", "int", 0) == 0:
            sourceUrls[0] = configHandler.read("source1", "url", "string",
                                               "file:///home/feibot/ubuntu/streams/feibot_1_4.mp4")
            frameWidth = configHandler.read("source1", "width", "int", 1920)
            frameHeight = configHandler.read("source1", "height", "int", 1080)
        else:
            sourceUrls[0] = configHandler.read("source1", "urlMp4", "string",
                                               "file:///home/feibot/ubuntu/streams/feibot_1_4.mp4")
            frameWidth = configHandler.read("source1", "widthMp4", "int", 1920)
            frameHeight = configHandler.read("source1", "heightMp4", "int", 1080)

    if configHandler.read("source2", "enable") == "1":
        if configHandler.read("source2", "useExampleMp4", "int", 0) == 0:
            sourceUrls[1] = configHandler.read("source2", "url", "string",
                                               "file:///home/feibot/ubuntu/streams/feibot_1_4.mp4")
        else:
            sourceUrls[1] = configHandler.read("source2", "urlMp4", "string",
                                               "file:///home/feibot/ubuntu/streams/feibot_1_4.mp4")

    if configHandler.read("source3", "enable") == "1":
        if configHandler.read("source3", "useExampleMp4", "int", 0) == 0:
            sourceUrls[2] = configHandler.read("source3", "url", "string",
                                               "file:///home/feibot/ubuntu/streams/feibot_1_4.mp4")
        else:
            sourceUrls[2] = configHandler.read("source3", "urlMp4", "string",
                                               "file:///home/feibot/ubuntu/streams/feibot_1_4.mp4")

    if configHandler.read("source4", "enable") == "1":
        if configHandler.read("source4", "useExampleMp4", "int", 0) == 0:
            sourceUrls[3] = configHandler.read("source4", "url", "string",
                                               "file:///home/feibot/ubuntu/streams/feibot_1_4.mp4")
        else:
            sourceUrls[3] = configHandler.read("source4", "urlMp4", "string",
                                               "file:///home/feibot/ubuntu/streams/feibot_1_4.mp4")

    return sourceUrls, frameWidth, frameHeight


import cv2
import numpy as np


def gaussian_blur_circle(image, blur_strength):
    # 获取图像的尺寸
    height, width = image.shape[:2]

    blur_strength = blur_strength * 2 + 1

    # 创建一个空的掩码图像，大小与原图相同，单通道（灰度）
    mask = np.zeros((height, width), dtype=np.uint8)

    # 在掩码上绘制一个白色的圆
    # cv2.circle(mask, (x_center, y_center), radius, 255, -1)  # -1 表示填充圆
    cv2.ellipse(mask, (width // 2, height // 2), (width // 2, height // 2), 0, 0, 360, 255, -1)  # -1 表示填充圆

    # 对原图进行高斯模糊（注意：这里是对整个图像进行模糊，然后我们会用掩码来提取圆形区域）
    blurred_image = cv2.GaussianBlur(image, (blur_strength, blur_strength), 0)

    # 创建一个空的输出图像，大小与原图相同，三通道（彩色）
    output_image = np.zeros_like(image)

    # 对于每个通道，应用掩码来混合原图和模糊图
    for c in range(image.shape[-1]):  # 假设图像是彩色的，有三个通道
        # 使用掩码来提取圆形区域内的模糊部分
        blurred_region = blurred_image[:, :, c] * (mask / 255)
        # 使用掩码的补集来提取圆形区域外的原始部分
        original_region = image[:, :, c] * (1 - (mask / 255))
        # 将两部分组合起来
        output_image[:, :, c] = blurred_region + original_region

    # 返回处理后的图像
    return output_image


# 计算两个矩形的IOU
def getOverlap(x1, y1, w1, h1, x2, y2, w2, h2):
    overlap_x = max(0, min(x1 + w1, x2 + w2) - max(x1, x2))
    overlap_y = max(0, min(y1 + h1, y2 + h2) - max(y1, y2))

    # 如果没有交集，overlap_x 和 overlap_y 为0，返回0
    overlap_area = overlap_x * overlap_y
    return overlap_area
