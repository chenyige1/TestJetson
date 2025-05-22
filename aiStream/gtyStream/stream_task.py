#!/usr/bin/env python3

################################################################################
# this is a feibot product
################################################################################

import sys
from pathlib import Path

sys.path.append('../../')
sys.path.append(str(Path(__file__).resolve().parent))
import configparser

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import GLib, Gst, GstRtspServer
from common.platform_info import PlatformInfo

import os
os.environ["GST_DEBUG_DUMP_DOT_DIR"] = "./tmp"
os.putenv('GST_DEBUG_DUMP_DIR_DIR', 'tmp')

from gtyStreamUtils import *

from gtyOsdProbe import *
from gtyTilterProbe import  *
from gtyNvvidconv1Probe import *
from multiprocessing import Lock

os.system("export GST_DEBUG=\"deepstream*:WARNING\"")

bitrate = 4000000

from colorama import Fore

from gtyIO import gtyLog

def main(eventQ=None):

    gtyLog.logger.info(Fore.GREEN+"====================Stream started=================="+Fore.RESET)

    #读取配置文件
    configHandler = gtyConfig.ConfigFileHandler()
    if not configHandler.saftyCheck:
        gtyLog.logger.critical(Fore.RED+"safty check failed..."+Fore.RESET)
        return

    sourceUrls,frameWidth,frameHeight =   loadSourceConfig(configHandler)

    number_sources = 0
    for s in sourceUrls:
        if s is not None:
            number_sources += 1


    tilterOutputWidth = configHandler.read("display","tilterOutputWidth","int",960)
    tilterOutputHeight= configHandler.read("display","tilterOutputHeight","int",540)
    asFastAsPossible = configHandler.read("display","asFastAsPossible","int",1)

    eventQ = eventQ
    lock = Lock()

    # 从eventQ中读出output路径
    outputPath = ''
    while True:
        with lock:
            if not eventQ["STREAM"].empty():
                event = eventQ['STREAM'].get(block=True, timeout=1)
                if event[0] == 'outputPath':
                    outputPath = event[1]
                time.sleep(0.1)
                break

    is_live = False
    platform_info = PlatformInfo()

    GObject.threads_init()
    Gst.init(None)
    ############################################
    #一、创建不同的组件
    ############################################
    pipeline = Gst.Pipeline()

    streammux = Gst.ElementFactory.make("nvstreammux", "Stream-muxer")
    pipeline.add(streammux)
    streammux.set_property("batched-push-timeout",int(1000000/60))

    # 设置多个输入源
    uri_decode_bins = []
    for i in range(len(sourceUrls)):
        sourceUrl = sourceUrls[i]
        if sourceUrl is None:
            continue
        if  sourceUrl.find("rtsp://") == 0:
            is_live = True
        source_bin,uri_decode_bin = create_source_bin(i,Gst, sourceUrl,outputPath)
        uri_decode_bins.append(uri_decode_bin)
        if not source_bin:
            sys.stderr.write("Unable to create source bin \n")
        pipeline.add(source_bin)
        padname = "sink_%u" % i
        sinkpad = streammux.request_pad_simple(padname)
        if not sinkpad:
            sys.stderr.write("Unable to create sink pad bin \n")
        srcpad = source_bin.get_static_pad("src")
        if not srcpad:
            sys.stderr.write("Unable to create src pad bin \n")
        srcpad.link(sinkpad)

    queue1 = Gst.ElementFactory.make("queue", "queue1")
    queue2 = Gst.ElementFactory.make("queue", "queue2")
    queue3 = Gst.ElementFactory.make("queue", "queue3")
    queue4 = Gst.ElementFactory.make("queue", "queue4")
    queue5 = Gst.ElementFactory.make("queue", "queue5")
    queue6 = Gst.ElementFactory.make("queue", "queue6")
    queue7 = Gst.ElementFactory.make("queue", "queue7")
    queue8 = Gst.ElementFactory.make("queue", "queue8")
    queue9 = Gst.ElementFactory.make("queue", "queue9")
    queue10 = Gst.ElementFactory.make("queue", "queue10")
    queue11 = Gst.ElementFactory.make("queue", "queue11")

    pgie = Gst.ElementFactory.make("nvinfer", "primary-inference")
    tracker = Gst.ElementFactory.make("nvtracker", "tracker")
    sgie1 = Gst.ElementFactory.make("nvinfer", "secondary1-nvinference-engine")

    caps1 = Gst.Caps.from_string("video/x-raw(memory:NVMM), format=RGBA")

    filter1 = Gst.ElementFactory.make("capsfilter", "filter1")

    tilterRowNum = int((number_sources-1)/2)+1
    tilterColNum = 2
    # 将视频编码流合成为2d切片,并将流数据转换为I420
    if number_sources > 1:
        tiler = Gst.ElementFactory.make("nvmultistreamtiler", "nvtiler")
        pipeline.add(tiler)

    nvvidconv = Gst.ElementFactory.make("nvvideoconvert", "convertor")

    nvosd = Gst.ElementFactory.make("nvdsosd", "onscreendisplay")

    tee = Gst.ElementFactory.make("tee","tee")

    nvvidconv_postosd = Gst.ElementFactory.make("nvvideoconvert", "convertor_postosd")

    caps = Gst.ElementFactory.make("capsfilter", "filter")

    caps.set_property("caps", Gst.Caps.from_string("video/x-raw(memory:NVMM), format=I420"))

    encoderRecord = Gst.ElementFactory.make("nvv4l2h264enc", "encoderRecord")

    nvvidconv1 = Gst.ElementFactory.make("nvvideoconvert", "convertor1")

    # 对于不同的平台，创建不同的终点
    # nv3dsink 用于将视频通过GPU加速显示到屏幕，是渲染输出的重要插件
    sink = Gst.ElementFactory.make("nv3dsink", "nv3d-sink")

    # 保存到文件的组件
    tee2 = Gst.ElementFactory.make("tee","tee2")

    h264parse = Gst.ElementFactory.make("h264parse", "h264-parse")

    splitMuxSink = Gst.ElementFactory.make("splitmuxsink","splitmuxsink")

    # 输出到udp前台页面组件
    rtph264pay = Gst.ElementFactory.make("rtph264pay")
    udpSink = Gst.ElementFactory.make("udpsink")

    pipeline.add(queue1)
    pipeline.add(queue2)
    pipeline.add(queue3)
    pipeline.add(queue4)
    pipeline.add(queue5)
    pipeline.add(queue6)
    pipeline.add(queue7)
    pipeline.add(queue8)
    pipeline.add(queue9)
    pipeline.add(queue10)
    pipeline.add(queue11)
    pipeline.add(pgie)
    pipeline.add(tracker)
    pipeline.add(sgie1)
    pipeline.add(nvvidconv)
    pipeline.add(filter1)
    pipeline.add(nvvidconv1)
    pipeline.add(nvosd)
    pipeline.add(sink)
    pipeline.add(tee)
    pipeline.add(nvvidconv_postosd)
    pipeline.add(caps)
    pipeline.add(encoderRecord)
    #保存到文件的组件
    pipeline.add(tee2)
    pipeline.add(h264parse)
    pipeline.add(splitMuxSink)
    # 输出到udp组件
    pipeline.add(udpSink)
    pipeline.add(rtph264pay)

    ############################################
    #二、设置组件属性
    ############################################
    filter1.set_property("caps", caps1)

    encoderRecord.set_property('bitrate', 10000000)
    # 设置编码的预设级别，影响编码速度和输出质量 0超快1快 最大性能模式
    encoderRecord.set_property('preset-level', 1)
    encoderRecord.set_property('maxperf-enable', 1)
    encoderRecord.set_property('insert-sps-pps', 1)
    encoderRecord.set_property("insert-vui",1)

    #============设置属性调试super start================
    streammux.set_property('nvbuf-memory-type', 4)
    tracker.set_property('compute-hw',2) # 1，gpu模式；2.vic模式
    tracker.set_property('display-tracking-id',1) # 追踪ID显示
    nvosd.set_property('process-mode', 2)  # 0,cpu模式；1，gpu模式；2.vic模式
    #-----设置nvvideoconvert-------
    nvvidconv.set_property('compute-hw',2)
    nvvidconv.set_property('copy-hw',2)
    nvvidconv_postosd.set_property('compute-hw',2)
    nvvidconv_postosd.set_property('copy-hw',2)
    nvvidconv1.set_property('compute-hw',2)
    nvvidconv1.set_property('copy-hw',2)
    nvvidconv.set_property('nvbuf-memory-type',4)
    nvvidconv_postosd.set_property('nvbuf-memory-type',4)
    nvvidconv1.set_property('nvbuf-memory-type',4)

    # ============设置属性调试super end==================



    sink.set_property('async', asFastAsPossible)
    sink.set_property('sync', (asFastAsPossible+1)%2)

    splitMuxSink.set_property("location",
                              f"{outputPath}/record_{datetime.datetime.now().strftime('%Y-%m-%d_%Hh%Mm%Ss')}"+"_%04d.mp4")
    splitMuxSink.set_property("max-size-time",60000000000)


    # 输入视频的尺寸，这里是单个画面的输入尺寸
    streammux.set_property('width', frameWidth)
    streammux.set_property('height', frameHeight)
    streammux.set_property('batch-size',number_sources) # 这里必须和输入的路数相同，否则会加速或减慢
    streammux.set_property('batched-push-timeout', MUXER_BATCH_TIMEOUT_USEC)
    streammux.set_property('buffer-pool-size',100)
    streammux.set_property('attach-sys-ts',1)
    streammux.set_property('compute-hw',2) #gpu1,vic2
    if is_live:
        gtyLog.logger.info("检测到实时视频流")
        streammux.set_property('live-source', 1)
        streammux.set_property('sync-inputs',0)
    else:
        streammux.set_property('sync-inputs',1)

    # 推理器
    pgie.set_property('config-file-path',
                      "./gtyStream/configFiles/config_jetson_infer_primary.txt")
    sgie1.set_property('config-file-path',
                       "./gtyStream/configFiles/config_jetson_infer_secondary_bib.txt")

    # 追踪器
    config = configparser.ConfigParser()
    config.read('./gtyStream/configFiles/dstest2_tracker_config.txt')
    config.sections()

    for key in config['tracker']:
        if key == 'tracker-width' :
            tracker.set_property('tracker-width', config.getint('tracker', key))
        if key == 'tracker-height' :
            tracker.set_property('tracker-height', config.getint('tracker', key))
        if key == 'gpu-id' :
            tracker.set_property('gpu_id', config.getint('tracker', key))
        if key == 'll-lib-file' :
            tracker.set_property('ll-lib-file', config.get('tracker', key))
        if key == 'll-config-file' :
            tracker.set_property('ll-config-file', config.get('tracker', key))
    tracker.set_property('user-meta-pool-size', 640)

    nvosd.set_property('process-mode',0) # 0,cpu模式；1，gpu模式；2.vic模式

    udpSink.set_property('host','127.0.0.1')
    udpSink.set_property('port',5599)
    udpSink.set_property('async', asFastAsPossible)
    udpSink.set_property('sync', (asFastAsPossible+1)%2)

    if number_sources > 1:
        tiler.set_property("rows", tilterRowNum)
        tiler.set_property("columns",tilterColNum)
        # 这里是画面的总高度、宽度
        tiler.set_property("width", tilterOutputWidth*tilterColNum)
        tiler.set_property("height", tilterOutputHeight*tilterRowNum)
        tiler.set_property('compute-hw',2) #gpu 1, vic 2


    ############################################
    #三、连接管道上组件
    ############################################

    streammux.link(queue1)
    queue1.link(pgie)
    pgie.link(queue2)
    queue2.link(tracker)
    tracker.link(sgie1)
    sgie1.link(queue3)
    queue3.link(nvvidconv1)
    nvvidconv1.link(queue4)
    queue4.link(filter1)
    filter1.link(queue5)

    if number_sources>1:
        queue5.link(tiler)
        tiler.link(nvvidconv)
    else:
        queue5.link(nvvidconv)

    nvvidconv.link(queue6)
    queue6.link(nvosd)
    nvosd.link(queue7)

    queue7.link(tee)

    tee.link(queue8)
    queue8.link(sink)

    # 对视频进行编码
    tee.link(queue9)
    queue9.link(nvvidconv_postosd)
    nvvidconv_postosd.link(caps)
    caps.link(encoderRecord)
    encoderRecord.link(tee2)


    # 输出到文件
    tee2.link(queue11)
    queue11.link(h264parse)
    h264parse.link(splitMuxSink)

    # 输出到udpSink
    tee2.link(rtph264pay)
    rtph264pay.link(udpSink)

    ############################################
    #四、创建主循环
    ############################################
    # create and event loop and feed gstreamer bus mesages to it
    loop = GLib.MainLoop()

    bus = pipeline.get_bus()
    bus.add_signal_watch()


    gtyData={
            # osd 参数
             "osdFrameCounter":0,
            # 画面比例调整系数
            "T":Transformer(frameWidth,frameHeight,tilterOutputWidth,tilterOutputHeight),
            # 运动员识别
            "runnersInFrame": [None,None,None,None],
            "runnersTracking": [RunnersTracking(0,eventQ),RunnersTracking(1,eventQ),
                                RunnersTracking(2,eventQ),RunnersTracking(3,eventQ)],
            "last5FrameTime":time.perf_counter(),
             "fps":25,
            "sourceFps":[{"last5Time":0,"counter":0,"fps":30},
                         {"last5Time":0,"counter":0,"fps":30},
                         {"last5Time":0,"counter":0,"fps":30},
                         {"last5Time":0,"counter":0,"fps":30}],
             "Gst":Gst,
             "platform_info":platform_info,
             "originalFrameSize":{"width":frameWidth,"height":frameHeight},
             "sourceNum":number_sources,
            "eventQ":eventQ
             }



    #nvvidconv1回调函数
    nvvidconv1.get_static_pad("sink").add_probe(Gst.PadProbeType.BUFFER, nvvidconv1_sink_pad_buffer_probe, gtyData)

    # 增加tilter回调函数
    if number_sources>1:
        tiler.get_static_pad("sink").add_probe(Gst.PadProbeType.BUFFER, tiler_sink_pad_buffer_probe, gtyData)
    else:
        nvvidconv.get_static_pad("sink").add_probe(Gst.PadProbeType.BUFFER, tiler_sink_pad_buffer_probe, gtyData)

    # 增加osd回调函数
    nvosd.get_static_pad("sink").add_probe(Gst.PadProbeType.BUFFER, osd_sink_pad_buffer_probe, gtyData)

    # 在管道状态变化或异常时调用：
    # Gst.debug_bin_to_dot_file(pipeline, Gst.DebugGraphDetails.ALL, "pipeline_snapshot")

    # 启动流水线
    pipeline.set_state(Gst.State.PLAYING)

    def stop_pipeline(pipeline):
        """停止GStreamer管道并释放资源"""
        for uri_decode_bin in uri_decode_bins:
            uri_decode_bin.emit('stop-sr', 0)
        if pipeline:
            pipeline.set_state(Gst.State.NULL)
            pipeline = None
    try:
        loop.run()

    except KeyboardInterrupt:
        gtyLog.logger.debug("keyboard interrupt received, shutting down")
        stop_pipeline(pipeline)
        # for uri_decode_bin in uri_decode_bins:
        #     uri_decode_bin.emit('stop-sr',0)
    except Exception as e:
        gtyLog.logger.debug(f"An unexpected error: {e}")
        stop_pipeline(pipeline)

    finally:
        # 清理和释放资源
        stop_pipeline(pipeline)
        # pipeline.set_state(Gst.State.NULL)

    # cleanup
    stop_pipeline(pipeline)
    # pipeline.set_state(Gst.State.NULL)

if __name__ == '__main__':
    sys.exit(main(sys.argv))

