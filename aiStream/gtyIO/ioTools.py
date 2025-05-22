import hashlib
import os
import time


def recordEpcDefaultFormat(fileUrl, data):
    if data is None or len(data) == 0:
        return False
    # 首先打开文件
    try:
        f = open(fileUrl, 'a')
    except Exception as e:
        os.system("touch " + fileUrl)
        return False

    # 对于每一条EPC值记录一行，写入csv中
    line = ("id=" + str(data[0]) +
            "," + "randomId=" + data[1] +
            "," + "cam=" + str(data[7]) +
            "," + "frame=" + str(data[8]) +
            "," + "bib=" + data[2] +
            "," + "info=" + data[3] +
            "," + "timeString=" + data[4] +
            "," + "picName=runner_" + data[5] + ".jpg"
            )
    try:
        f.write(line)
        f.write('\n')
    except Exception as e:
        pass
    f.flush()
    f.close()


def get_token(stra, secret=''):
    md5str = str(stra) + secret
    m1 = hashlib.md5()
    m1.update(md5str.encode("utf-8"))
    token = m1.hexdigest()
    return token


def resizeToRatio(image, ratio):
    h, w = image.shape[:2]
    centerH = int(h / 2)
    centerW = int(w / 2)
    if h > w * ratio:
        # 高度方向富裕
        h2 = int(w * ratio)
        return image[max(0, int(centerH - h2 / 2)):min(int(centerH + h2 / 2), h)]
    else:
        # 宽度方向富裕
        w2 = int(h / ratio)
        return image[:, max(0, int(centerW - w2 / 2)):min(int(centerW + w2 / 2), w)]


# 检查磁盘容量，如果可用容量小于100GB则删除之前的运行存储文件，直到可用容量大于100GB

import shutil
from gtyIO import gtyLog

def remove_original(current_folder, files, sources):
    # 找到所有以 "original_" 开头的文件，并按文件名排序
    original_files = sorted([f for f in files if f.startswith("original_")])

    # 删除最多 sources 个文件
    deleted_count = 0
    for original_file in original_files:
        if deleted_count >= sources:
            break  # 如果已经删除了 sources 个文件，停止循环

        file_path = os.path.join(current_folder, original_file)
        try:
            gtyLog.logger.info(f"{file_path} has been deleted.")
            os.remove(file_path)
            deleted_count += 1
        except Exception as e:
            gtyLog.logger.error(f"Failed to delete {file_path}: {e}")

    if deleted_count == 0:
        gtyLog.logger.info("current no original_")
    else:
        gtyLog.logger.info(f"Deleted {deleted_count} original_ files.")

def removeRunFilesWhenDiskFull(current_folder=None, number_sources=1):
    """
    directories中的非current_folder首个文件夹移除(非文件夹跳过)
    只有一个当前文件夹时,将录制视频从早到晚删original几路删几个 1个record
    """
    print("number_sources", number_sources, os.path.realpath(current_folder))
    while True:
        try:
            diskSpace = shutil.disk_usage('/')
            freeDiskSpace = int(diskSpace[2] / (1024.0 * 1024.0 * 1024.0) * 100) / 100.0
            gtyLog.logger.info("free disk space", freeDiskSpace, "GB")
            if freeDiskSpace < 100:
                # 删除一些运行数据，使得磁盘空间大于100GB
                directories = ["/home/feibot/feibot/aiStream/aiStream/output/",
                               "/home/feibot/feibot/aiStream/output/",
                               "/home/feibot/feibot/testv2/feibot-ai-stream/output/",
                               "/home/feibot/feibot/feibot-ai-stream/output/",]
                for directory in directories:
                    if os.path.isdir(directory):
                        folders = sorted(os.listdir(directory))
                        if folders:
                            for file in folders:
                                first_folder = os.path.join(directory, file)
                                # 文件夹不为当前文件夹就删整个文件夹
                                if os.path.isdir(first_folder) and os.path.realpath(current_folder) != os.path.realpath(first_folder):
                                    # 删除第一个文件夹
                                    shutil.rmtree(first_folder)
                                    gtyLog.logger.info(f"Folder {first_folder} has been deleted.")
                                    break
                                # 只剩当前文件夹情况(若不空则删除其中视频-有视频情况下)
                                elif os.path.realpath(current_folder) == os.path.realpath(first_folder):
                                    files = sorted(os.listdir(current_folder))
                                    # 删除前n个 original_ 文件
                                    remove_original(current_folder, files, number_sources)
                                    # 删除第一个 record_ 文件 next直接获取迭代器的第一个元素
                                    try:
                                        record_index = next(i for i, f in enumerate(files) if f.startswith("record_"))
                                        first_record = os.path.join(current_folder, files[record_index])
                                        gtyLog.logger.info(f"{first_record} has been deleted.")
                                        os.remove(first_record)
                                    except StopIteration:
                                        gtyLog.logger.info("current no record_")
                                    break
                        else:
                            gtyLog.logger.info(f"{folders} is not folder")
                    else:
                        gtyLog.logger.info(f"{directory} No folders found.")
        except Exception as e:
            gtyLog.logger.error(e)
            pass

        # 每30秒监控一次
        time.sleep(30)
