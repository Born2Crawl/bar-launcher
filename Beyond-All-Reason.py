#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import os
import wx
import wx.adv
import sys
import json
import stat
import time
import logging
import platform
import pyperclip
import requests
import subprocess
from urllib.parse import urlparse
from threading import *

# AWS S3 upload
import boto3
from botocore.exceptions import ClientError

game_name = 'Beyond All Reason'
log_file_name = 'bar-launcher.log'
logs_bucket = 'bar-infologs'
logs_url = f'https://{logs_bucket}.s3.amazonaws.com/'

# Global variable for a child process. Since we're running everything sequentially, "there can be only one" (c)
child_process = None

main_frame = None # global variable for a window to send all events to

# Custom event to notify about Update/Start execution finished
EVT_EXEC_FINISHED_ID = int(wx.NewIdRef(count=1))

def EVT_EXEC_FINISHED(win, func):
    win.Connect(-1, -1, EVT_EXEC_FINISHED_ID, func)

class ExecFinishedEvent(wx.PyEvent):
    def __init__(self, data):
        wx.PyEvent.__init__(self)
        self.SetEventType(EVT_EXEC_FINISHED_ID)
        self.data = data

# Custom event to notify about log upload finished
EVT_LOG_UPLOADED_ID = int(wx.NewIdRef(count=1))

def EVT_LOG_UPLOADED(win, func):
    win.Connect(-1, -1, EVT_LOG_UPLOADED_ID, func)

class LogUploadedEvent(wx.PyEvent):
    def __init__(self, data):
        wx.PyEvent.__init__(self)
        self.SetEventType(EVT_LOG_UPLOADED_ID)
        self.data = data

# Custom event to update the status text
EVT_STATUS_UPDATE_ID = int(wx.NewIdRef(count=1))

def EVT_STATUS_UPDATE(win, func):
    win.Connect(-1, -1, EVT_STATUS_UPDATE_ID, func)

class StatusUpdateEvent(wx.PyEvent):
    def __init__(self, data):
        wx.PyEvent.__init__(self)
        self.SetEventType(EVT_STATUS_UPDATE_ID)
        self.data = data

# Custom event to update the progress bar
EVT_PROGRESS_UPDATE_ID = int(wx.NewIdRef(count=1))

def EVT_PROGRESS_UPDATE(win, func):
    win.Connect(-1, -1, EVT_PROGRESS_UPDATE_ID, func)

class ProgressUpdateEvent(wx.PyEvent):
    def __init__(self, data):
        wx.PyEvent.__init__(self)
        self.SetEventType(EVT_PROGRESS_UPDATE_ID)
        self.data = data

# Custom event to minimize the main window
EVT_ICONIZE_WINDOW_ID = int(wx.NewIdRef(count=1))

def EVT_ICONIZE_WINDOW(win, func):
    win.Connect(-1, -1, EVT_ICONIZE_WINDOW_ID, func)

class IconizeWindowEvent(wx.PyEvent):
    def __init__(self, data):
        wx.PyEvent.__init__(self)
        self.SetEventType(EVT_ICONIZE_WINDOW_ID)
        self.data = data

# Custom event to catch logger messages and add them to text control
EVT_LOGGER_MSG_ID = int(wx.NewIdRef(count=1))

def EVT_LOGGER_MSG(win, func):
    win.Connect(-1, -1, EVT_LOGGER_MSG_ID, func)

class LoggerMsgEvent(wx.PyEvent):
    def __init__(self, message, levelname):
        wx.PyEvent.__init__(self)
        self.SetEventType(EVT_LOGGER_MSG_ID)
        self.message = message
        self.levelname = levelname

# Custom logging handler to send logger events
class LoggerToTextCtlHandler(logging.StreamHandler):
    def emit(self, record):
        message = self.format(record)
        event = LoggerMsgEvent(message=message, levelname=record.levelname)
        if main_frame:
            wx.PostEvent(main_frame, event)

logger = logging.getLogger()
log_formatter_short = logging.Formatter('%(message)s')
log_formatter_long = logging.Formatter('%(asctime)s %(levelname)s %(message)s')

log_console_handler = logging.StreamHandler(sys.stdout)
log_console_handler.setFormatter(log_formatter_short)
logger.addHandler(log_console_handler)

log_text_ctl_handler = LoggerToTextCtlHandler()
log_text_ctl_handler.setFormatter(log_formatter_short)
logger.addHandler(log_text_ctl_handler)

log_file_handler = logging.FileHandler(log_file_name, mode='w')
log_file_handler.setFormatter(log_formatter_long)
logger.addHandler(log_file_handler)

logger.setLevel(logging.INFO)

class FileManager():
    def get_current_dir(self):
        return os.getcwd()

    def join_path(self, *args):
        return os.path.join(*args)

    def split_extension(self, path):
        return os.path.splitext(path)

    def extract_dir_name(self, path):
        return os.path.dirname(path)

    def get_full_path(self, filename):
        return os.path.realpath(filename)

    def extract_filename(self, path):
        return os.path.basename(path)

    def file_exists(self, path):
        return os.path.isfile(path)

    def dir_exists(self, path):
        return os.path.isdir(path)

    def make_dirs(self, path):
        return os.makedirs(path, exist_ok=True)

    def rename(self, current_path, new_path):
        return os.rename(current_path, new_path)

    def remove(self, path):
        global logger

        try:
            return os.remove(path)
        except:
            logger.error('Couldn\'t remove!')
            e = str(sys.exc_info()[1])
            logger.error(e)

    def remove_dir(self, path):
        global logger

        try:
            return os.rmdir(path)
        except:
            logger.error('Couldn\'t remove!')
            e = str(sys.exc_info()[1])
            logger.error(e)

file_manager = FileManager()

class PlatformManager():
    current_platform = platform.system()
    current_dir = file_manager.get_current_dir()
    data_dir = file_manager.join_path(current_dir, 'data')
    executable_dir = file_manager.join_path(current_dir, 'bin')

    resources = {
        'launcher_config': {
            'url': 'https://raw.githubusercontent.com/beyond-all-reason/BYAR-Chobby/master/dist_cfg/config.json',
            'path': file_manager.join_path(current_dir, 'config.json'),
        },
        'lobby_config': {
            'url': 'https://raw.githubusercontent.com/beyond-all-reason/BYAR-Chobby/master/dist_cfg/files/chobby_config.json',
            'path': file_manager.join_path(data_dir, 'chobby_config.json'),
        },
        'background_image': {
            'url': 'https://raw.githubusercontent.com/Born2Crawl/bar-launcher/main/resources/background.png',
            'path': file_manager.join_path(current_dir, 'resources', 'background.png'),
        },
        'icon_image': {
            'url': 'https://raw.githubusercontent.com/Born2Crawl/bar-launcher/main/resources/icon.png',
            'path': file_manager.join_path(current_dir, 'resources', 'icon.png'),
        },
        'font_file': {
            'url': 'https://raw.githubusercontent.com/Born2Crawl/bar-launcher/main/resources/fonts/Poppins-Bold.ttf',
            'path': file_manager.join_path(current_dir, 'resources', 'fonts', 'Poppins-Bold.ttf'),
        },
    }

    def get_resource_path(self, resource_name):
        return self.resources[resource_name]['path']

    def get_resource_url(self, resource_name):
        return self.resources[resource_name]['url']

    def ensure_resource_exists(self, resource_name, force_download_fresh=True, ignore_download_fail=True):
        resource_path = self.get_resource_path(resource_name)

        if not force_download_fresh and file_manager.file_exists(resource_path):
            logger.info(f'File {resource_path} already exists, skipping download...')
            return True

        resource_url = self.get_resource_url(resource_name)
        if not http_downloader.download_file(resource_url, resource_path):
            if (ignore_download_fail and file_manager.file_exists(resource_path)):
                logger.error(f'Downloading {resource_name} failed, will use the existing file!')
                return True
            else:
                raise Exception(f'Couldn\'t find or download the {resource_name} to use!')

        return True

    platform_binaries = {
        'Windows': {
            '7zip': {
                'command': ['7z_win64.exe'],
                'path': 'bin',
                'downloads': [
                    'https://github.com/Born2Crawl/bar-launcher/raw/main/bin/7z_win64.exe',
                ],
            },
            'pr_downloader': {
                'command': ['pr-downloader.exe'],
                'path': 'bin',
                'downloads': [
                    'https://github.com/Born2Crawl/bar-launcher/raw/main/bin/pr-downloader.exe',
                    'https://github.com/Born2Crawl/bar-launcher/raw/main/bin/libcurl.dll',
                    'https://github.com/Born2Crawl/bar-launcher/raw/main/bin/zlib1.dll',
                ],
            },
            'spring': {
                'command': ['spring.exe'],
            },
            'file_manager': {
                'command': ['explorer'],
            },
        },
        'Linux': {
            '7zip': {
                'command': ['7zz_linux_x86-64'],
                'path': 'bin',
                'downloads': [
                    'https://github.com/Born2Crawl/bar-launcher/raw/main/bin/7zz_linux_x86-64',
                ],
            },
            'pr_downloader': {
                'command': ['pr-downloader'],
                'path': 'bin',
                'downloads': [
                    'https://github.com/Born2Crawl/bar-launcher/raw/main/bin/pr-downloader',
                ],
            },
            'spring': {
                'command': ['spring'],
            },
            'file_manager': {
                'command': ['xdg-open'],
            },
        },
        'Darwin': {
            '7zip': {
                'command': ['7zz_macos'],
                'path': 'bin',
                'downloads': [
                    'https://github.com/Born2Crawl/bar-launcher/raw/main/bin/7zz_macos',
                ],
            },
            'pr_downloader': {
                'command': ['pr-downloader-mac'],
                'path': 'bin',
                'downloads': [
                    'https://github.com/Born2Crawl/bar-launcher/raw/main/bin/pr-downloader-mac',
                    # These need to go to ../lib/
                    'https://github.com/Born2Crawl/bar-launcher/raw/main/libminizip.1.dylib',
                    'https://github.com/Born2Crawl/bar-launcher/raw/main/libstdc++.6.dylib',
                ],
            },
            'spring': {
                'command': ['spring'],
            },
            'file_manager': {
                'command': ['open', '-R'],
            },
        },
    }

    def get_executable_command(self, name):
        current_platform = self.current_platform
        current_dir = self.current_dir

        command = list(self.platform_binaries[current_platform][name]['command'])
        if 'path' in self.platform_binaries[current_platform][name]:
            command[0] = file_manager.join_path(current_dir, self.platform_binaries[current_platform][name]['path'], command[0])

        return command

    def download_executable(self, name):
        current_platform = self.current_platform
        executable_dir = self.executable_dir

        if not 'downloads' in self.platform_binaries[current_platform][name]:
            return

        command = self.get_executable_command(name)
        executable = command[0]

        if not file_manager.file_exists(executable):
            logger.warning(f'Executable wasn\'t found in: {executable}')
            logger.info('Downloading executable files...')
            file_manager.make_dirs(executable_dir)
            for url in self.platform_binaries[current_platform][name]['downloads']:
                if not http_downloader.download_file(url, executable_dir):
                    raise Exception('Couldn\'t download the archive extractor!')
            # Setting executable flag
            st = os.stat(executable)
            os.chmod(executable, st.st_mode | stat.S_IEXEC)

platform_manager = PlatformManager()

class ProcessStarter():
    def start_process(self, command, nowait=False):
        global main_frame
        global logger
        global child_process

        logger.info('Starting a process:')
        logger.info(' '.join(command))
        try:
            if nowait:
                subprocess.Popen(command)
                return True

            with subprocess.Popen(command, stdout=subprocess.PIPE) as proc:
                child_process = proc
                while True:
                    line = proc.stdout.readline()
                    if not line:
                        break
                    if len(line.rstrip()) > 0:
                        logger.info(line.rstrip().decode('utf-8'))

                #streamdata = proc.communicate()[0]
                proc.wait()

                child_process = None

                retcode = proc.returncode
                logger.info(f'Process ended with status {retcode}')

                return retcode == 0
        except:
            child_process = None
            logger.error('Process start failed!')
            e = str(sys.exc_info()[1])
            logger.error(e)
            return False

        return True

process_starter = ProcessStarter()

class ArchiveExtractor():
    def extract_7zip(self, archive_name, destination):
        global logger

        platform_manager.download_executable('7zip')

        zip_command = platform_manager.get_executable_command('7zip')
        zip_executable = zip_command[0]
        logger.info(f'Extracting archive: "{archive_name}" "{destination}"')
        zip_command.extend(['x', archive_name, '-y', f'-o{destination}'])
        return process_starter.start_process(zip_command)

archive_extractor = ArchiveExtractor()

class HttpDownloader():
    def download_file(self, source_url, target):
        global logger

        logger.info(f'Downloading: "{source_url}" to: "{target}"')
        try:
            if file_manager.dir_exists(target): # Target is a directory, adding a filename from the URL to it
                target_file = file_manager.join_path(target, file_manager.extract_filename(urlparse(source_url).path))
            else:
                target_file = target

            logger.info(f'Creating directories for "{target_file}" if needed...')
            file_manager.make_dirs(file_manager.extract_dir_name(target_file))

            response = requests.get(source_url, allow_redirects=True, timeout=3)
            if response.status_code >= 300:
                raise Exception('Bad response: {status_code} ({content})'.format(status_code=str(response.status_code), content=response.content.decode('utf-8')))

            open(target_file, 'wb').write(response.content)
        except:
            logger.error('Download failed:')
            e = str(sys.exc_info()[1])
            logger.error(e)
            return False
        return True

http_downloader = HttpDownloader()

class PrDownloader():
    def download_game(self, data_dir, game_name):
        global logger

        platform_manager.download_executable('pr_downloader')

        logger.info(f'Downloading: "{game_name}" to: "{data_dir}"')
        command = platform_manager.get_executable_command('pr_downloader')
        command.extend(['--filesystem-writepath', data_dir, '--download-game', game_name])
        return process_starter.start_process(command)

pr_downloader = PrDownloader()

# Thread class that executes logs upload
class LogUploaderThread(Thread):
    def __init__(self, file_name, bucket, object_name):
        Thread.__init__(self)
        self.file_name = file_name
        self.bucket = bucket
        self.object_name = object_name
        self.start()

    def run(self):
        global main_frame
        global logger

        file_name = self.file_name
        bucket = self.bucket
        object_name = self.object_name

        try:
            resp = requests.get(f'{logs_url}c', allow_redirects=True)
            c = resp.json()
            s3_client = boto3.client(
                's3',
                aws_access_key_id=c['access_key_id'],
                aws_secret_access_key=c['secret_access_key']
            )
            logger.info(f'Uploading: "{file_name}" to: "{bucket}"')
            response = s3_client.upload_file(file_name, bucket, object_name, ExtraArgs={'ContentType': 'text/plain'})
            result = f'{logs_url}{object_name}'
            if main_frame:
                wx.PostEvent(main_frame, LogUploadedEvent(result))
        except:
            logger.error('Upload failed!')
            e = str(sys.exc_info()[1])
            logger.error(e)
            if main_frame:
                wx.PostEvent(main_frame, LogUploadedEvent(None))

class ClipboardManager():
    def copy(self, text):
        global logger

        try:
            logger.info(f'Copying to clipboard: "{text}"')
            pyperclip.copy(text)
        except:
            logger.error('Copying failed:')
            e = str(sys.exc_info()[1])
            logger.error(e)
            return False
        return True

clipboard_manager = ClipboardManager()

class ConfigManager():
    compatible_configs = []
    current_config = {}

    def __init__(self, *args, **kwds):
        self.compatible_configs = self.get_compatible_configs()

    def read_config(self):
        global logger

        platform_manager.ensure_resource_exists('launcher_config', force_download_fresh=True, ignore_download_fail=True)
        launcher_config_path = platform_manager.get_resource_path('launcher_config')

        logger.info(f'Reading the config file from {launcher_config_path}')
        f = open(launcher_config_path)
        data = json.load(f)
        f.close()
        return data

    def get_compatible_configs(self):
        data = self.read_config()
        result = []

        if not 'setups' in data:
            raise Exception('Not a valid config file, missing "setups" section!')

        for setup in data['setups']:
            if not 'package' in setup or not 'platform' in setup['package'] or not 'launch' in setup:
                raise Exception('Not a valid config setup, missing "package->platform" or "launch" section!')

            if ((setup['package']['platform'] == 'win32' and platform_manager.current_platform == 'Windows') \
                    or (setup['package']['platform'] == 'linux' and platform_manager.current_platform == 'Linux') \
                    or (setup['package']['platform'] == 'darwin' and platform_manager.current_platform == 'Darwin')):
                result.append(setup)
        return result

    def get_compatible_configs_names(self):
        result = []
        for config in self.compatible_configs:
            result.append(config['package']['display'])
        return result

config_manager = ConfigManager()

# Thread class that executes Update/Start
class UpdaterStarterThread(Thread):
    data_dir = platform_manager.data_dir
    temp_archive_name = file_manager.join_path(data_dir, 'download.7z')

    def __init__(self, is_update):
        Thread.__init__(self)
        self.is_update = is_update
        self.start()

    def run(self):
        global main_frame
        global logger

        config = config_manager.current_config

        total_progress_steps = 2 # Without updating, only 2 steps (update lobby config and start)
        current_progres_step = 0

        def set_gauge_range(value):
            if main_frame:
                wx.PostEvent(main_frame, ProgressUpdateEvent({'range': value}))

        def set_gauge_progress(value):
            if main_frame:
                wx.PostEvent(main_frame, ProgressUpdateEvent({'value': value}))

        def set_status_text(current_step, total_steps, message):
            text = f'Step {current_step} out of {total_steps}: {message}'
            logger.info(text)
            if main_frame:
                wx.PostEvent(main_frame, StatusUpdateEvent(text))

        set_gauge_range(total_progress_steps)
        set_gauge_progress(current_progres_step)

        try:
            if self.is_update:
                pr_downloader_games = {}
                http_resources = {}
                launchers = []

                # Updating the game according to the current config
                if 'games' in config['downloads']:
                    for game in config['downloads']['games']:
                        pr_downloader_games.update({game: game})
                        total_progress_steps += 1

                if 'resources' in config['downloads']:
                    total_progress_steps += 1 # Only one step for all resources, as they are fast to update
                    for resource in config['downloads']['resources']:
                        http_resources.update({resource['url']: resource})

                set_gauge_range(total_progress_steps)

                logger.info('Updating the game repositories')
                for n in pr_downloader_games:
                    logger.info('================================================================================')
                    game = pr_downloader_games[n]

                    current_progres_step += 1
                    set_gauge_progress(current_progres_step)
                    set_status_text(current_progres_step, total_progress_steps, f'updating {game}')

                    if not pr_downloader.download_game(self.data_dir, game):
                        raise Exception(f'Error updating {n}!')

                logger.info('Updating the engine and additional resources')
                if len(http_resources) > 0:
                    current_progres_step += 1
                    set_gauge_progress(current_progres_step)

                for n in http_resources:
                    logger.info('================================================================================')
                    resource = http_resources[n]
                    destination = resource['destination']
                    destination_path = file_manager.join_path(self.data_dir, resource['destination'])

                    set_status_text(current_progres_step, total_progress_steps, f'updating {destination}')

                    if file_manager.file_exists(destination_path) or file_manager.dir_exists(destination_path):
                        logger.warning(f'"{destination_path}" already exists, skipping...')
                        continue

                    url = resource['url']
                    is_extract = 'extract' in resource and resource['extract']

                    if not http_downloader.download_file(url, self.temp_archive_name):
                        raise Exception(f'Error downloading: {url}!')

                    if is_extract:
                        if file_manager.file_exists(self.temp_archive_name):
                            logger.info(f'Creating directories: "{destination_path}"')
                            file_manager.make_dirs(destination_path)

                            if not archive_extractor.extract_7zip(self.temp_archive_name, destination_path):
                                file_manager.remove_dir(destination_path) # Removing a (hopefully) empty directory
                                raise Exception(f'Error extracting {self.temp_archive_name}!')

                            logger.info(f'Removing a temp file: "{self.temp_archive_name}"')
                            file_manager.remove(self.temp_archive_name)
                        else:
                            logger.info('Downloaded file didn\'t exist!')
                    else:
                        if file_manager.file_exists(self.temp_archive_name):
                            destination_path_dir = file_manager.extract_dir_name(destination_path)
                            logger.info(f'Creating directories: "{destination_path_dir}"')
                            file_manager.make_dirs(destination_path_dir)

                            logger.info(f'Renaming a temp file: "{self.temp_archive_name}" to: "{destination_path}"')
                            file_manager.rename(self.temp_archive_name, destination_path)
                        else:
                            logger.info('Downloaded file didn\'t exist!')

            logger.info('Updating lobby config')
            logger.info('================================================================================')

            current_progres_step += 1
            set_gauge_progress(current_progres_step)
            set_status_text(current_progres_step, total_progress_steps, 'updating lobby config')

            platform_manager.ensure_resource_exists('lobby_config', force_download_fresh=True, ignore_download_fail=True)

            logger.info('Starting the game')
            logger.info('================================================================================')

            current_progres_step += 1
            set_gauge_progress(current_progres_step)
            set_status_text(current_progres_step, total_progress_steps, 'starting the game')

            if main_frame:
                wx.PostEvent(main_frame, IconizeWindowEvent(True))

            # Starting the game
            start_args = config['launch']['start_args']
            engine = config['launch']['engine']
            engine_dir = file_manager.join_path(self.data_dir, 'engine', engine)
            spring_command = platform_manager.get_executable_command('spring')
            spring_command[0] = file_manager.join_path(engine_dir, spring_command[0])

            if not file_manager.dir_exists(engine_dir) or not file_manager.file_exists(spring_command[0]):
                if file_manager.dir_exists(engine_dir):
                    file_manager.remove_dir(engine_dir) # Trying to remove a (hopfully) empty directory since spring executable is not there
                raise Exception('Can\'t locate the engine version specified in the config file, please update to download it!')

            spring_command.extend(['--write-dir', self.data_dir, '--isolation'])
            spring_command.extend(start_args)
            if not process_starter.start_process(spring_command):
                raise Exception('Error while running the game!')

            logger.info('Process finished!')
            if main_frame:
                wx.PostEvent(main_frame, ExecFinishedEvent(None))
        except:
            logger.error('Error while updating/starting the game!')
            e = str(sys.exc_info()[1])
            logger.error(e)
            if main_frame:
                wx.PostEvent(main_frame, ExecFinishedEvent(e))


class CustomTaskBarIcon(wx.adv.TaskBarIcon):
    def __init__(self, frame, icon_path):
        wx.adv.TaskBarIcon.__init__(self)
        self.frame = frame
        self.icon = wx.Icon(wx.Bitmap(icon_path))

        self.SetIcon(self.icon, game_name)
        #self.Bind(wx.adv.EVT_TASKBAR_LEFT_DCLICK, self.OnToggleHide)

    def CreateMenuItem(self, menu, label, func):
        item = wx.MenuItem(menu, -1, label)
        menu.Bind(wx.EVT_MENU, func, id=item.GetId())
        menu.Append(item)
        return item

    def CreatePopupMenu(self):
        menu = wx.Menu()
        self.CreateMenuItem(menu, 'Toggle Hide', self.OnToggleHide)
        menu.AppendSeparator()
        self.CreateMenuItem(menu, 'Exit', self.OnTaskBarClose)
        return menu

    def OnTaskBarActivate(self, event):
        pass

    def IconizeWindow(self, is_iconize):
        if is_iconize:
            self.frame.Iconize(True)
            self.frame.Hide()
        else:
            self.frame.Show()
            self.frame.Restore()

    def OnToggleHide(self, event):
        self.IconizeWindow(not self.frame.IsIconized())

    def OnTaskBarClose(self, event):
        self.frame.Close()

class MainPanel(wx.Panel):
    def __init__(self, parent, background_path, font_path):
        wx.Panel.__init__(self, parent=parent)
        self.font_path = font_path
        self.SetBackgroundStyle(wx.BG_STYLE_CUSTOM)
        self.bg = wx.Image(background_path, wx.BITMAP_TYPE_ANY)
        self.proportion = self.bg.GetWidth() / self.bg.GetHeight()

        self.Bind(wx.EVT_SIZE, self.OnSize)
        self.Bind(wx.EVT_PAINT, self.OnPaint)

    def OnSize(self, size):
        self.Layout()
        self.Refresh()

    def OnPaint(self, event):
        dc = wx.BufferedPaintDC(self)
        self.Draw(dc)

    def Draw(self, dc):
        client_width, client_height = self.GetClientSize()
        if not client_width:
            return

        dc.Clear()
        client_height = int(client_width / self.proportion)
        scaled_background = self.bg.Scale(client_width, client_height, wx.IMAGE_QUALITY_HIGH)
        dc.DrawBitmap(wx.Bitmap(scaled_background), 0, 0)

        font = wx.Font(24, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, 0, "")
        try:
            if platform_manager.current_platform != 'Darwin' and font.AddPrivateFont(self.font_path):
                font.SetFaceName('Poppins')
        except AttributeError:
            pass
        dc.SetFont(font)
        dc.SetTextForeground(wx.BLACK)
        dc.DrawText(game_name, 32, 32)
        dc.SetTextForeground(wx.WHITE)
        dc.DrawText(game_name, 30, 30)

class LauncherFrame(wx.Frame):

    def __init__(self, *args, **kwds):
        global main_frame

        platform_manager.ensure_resource_exists('icon_image', force_download_fresh=False, ignore_download_fail=False)
        icon_path = platform_manager.get_resource_path('icon_image')
        platform_manager.ensure_resource_exists('background_image', force_download_fresh=False, ignore_download_fail=False)
        background_path = platform_manager.get_resource_path('background_image')
        platform_manager.ensure_resource_exists('font_file', force_download_fresh=False, ignore_download_fail=False)
        font_path = platform_manager.get_resource_path('font_file')

        kwds["style"] = kwds.get("style", 0) | wx.CAPTION | wx.CLIP_CHILDREN | wx.CLOSE_BOX | wx.MINIMIZE_BOX | wx.SYSTEM_MENU
        wx.Frame.__init__(self, *args, **kwds)
        self.SetSize((800, 380))
        self.SetTitle(game_name)

        self.panel_main = MainPanel(self, background_path, font_path)

        sizer_main_vert = wx.BoxSizer(wx.VERTICAL)

        sizer_top_horz = wx.BoxSizer(wx.HORIZONTAL)
        sizer_main_vert.Add(sizer_top_horz, 0, wx.ALL | wx.EXPAND, 4)

        sizer_title = wx.BoxSizer(wx.VERTICAL)
        sizer_top_horz.Add(sizer_title, 1, wx.EXPAND, 0)

        #label_title = wx.StaticText(self.panel_main, wx.ID_ANY, game_name)
        #label_title.SetFont(wx.Font(24, wx.FONTFAMILY_SCRIPT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, 0, ""))
        #sizer_title.Add(label_title, 0, wx.ALL, 24)

        sizer_top_horz.Add((20, 200), 1, wx.ALL | wx.EXPAND, 2)

        sizer_config = wx.BoxSizer(wx.VERTICAL)
        sizer_top_horz.Add(sizer_config, 0, wx.EXPAND, 0)

        label_config = wx.StaticText(self.panel_main, wx.ID_ANY, "Config:")
        sizer_config.Add(label_config, 0, wx.ALL, 2)

        self.combobox_config = wx.ComboBox(self.panel_main, wx.ID_ANY, choices=[], style=wx.CB_DROPDOWN | wx.CB_READONLY)
        self.combobox_config.SetMinSize((120, 23))
        sizer_config.Add(self.combobox_config, 0, wx.ALL, 2)

        sizer_top_horz.Add((20, 100), 0, 0, 0)

        sizer_bottom_horz = wx.BoxSizer(wx.HORIZONTAL)
        sizer_main_vert.Add(sizer_bottom_horz, 0, wx.ALL | wx.EXPAND, 4)

        sizer_bottom_horz.Add((20, 100), 0, 0, 0)

        sizer_bottom_left_vert = wx.BoxSizer(wx.VERTICAL)
        sizer_bottom_horz.Add(sizer_bottom_left_vert, 1, wx.EXPAND, 0)

        sizer_log_buttonz_horz = wx.BoxSizer(wx.HORIZONTAL)
        sizer_bottom_left_vert.Add(sizer_log_buttonz_horz, 0, wx.EXPAND, 0)

        self.button_log_toggle = wx.Button(self.panel_main, wx.ID_ANY, "Toggle Log")
        sizer_log_buttonz_horz.Add(self.button_log_toggle, 0, wx.ALL, 2)

        self.button_log_upload = wx.Button(self.panel_main, wx.ID_ANY, "Upload Log")
        sizer_log_buttonz_horz.Add(self.button_log_upload, 0, wx.ALL, 2)

        self.button_open_install_dir = wx.Button(self.panel_main, wx.ID_ANY, "Open Install Directory")
        sizer_log_buttonz_horz.Add(self.button_open_install_dir, 0, wx.ALL, 2)

        sizer_bottom_left_vert.Add((80, 20), 0, wx.ALL, 2)

        self.panel_status = wx.Panel(self.panel_main, wx.ID_ANY, style=wx.BORDER_STATIC)
        sizer_bottom_left_vert.Add(self.panel_status, 0, wx.ALL | wx.EXPAND, 2)

        sizer_status = wx.BoxSizer(wx.HORIZONTAL)

        self.label_update_status = wx.StaticText(self.panel_status, wx.ID_ANY, "Ready")
        sizer_status.Add(self.label_update_status, 0, wx.ALL, 2)

        self.gauge_progress = wx.Gauge(self.panel_main, wx.ID_ANY, 10)
        self.gauge_progress.SetMinSize((550, 15))
        sizer_bottom_left_vert.Add(self.gauge_progress, 0, wx.ALL | wx.EXPAND, 2)

        sizer_bottom_horz.Add((20, 100), 0, wx.ALL, 2)

        sizer_bottom_right_vert = wx.BoxSizer(wx.VERTICAL)
        sizer_bottom_horz.Add(sizer_bottom_right_vert, 0, 0, 0)

        self.button_start = wx.Button(self.panel_main, wx.ID_ANY, "Start")
        self.button_start.SetMinSize((120, 60))
        self.button_start.SetFont(wx.Font(14, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, 0, ""))
        sizer_bottom_right_vert.Add(self.button_start, 0, wx.ALL, 2)

        self.checkbox_update = wx.CheckBox(self.panel_main, wx.ID_ANY, "Update")
        sizer_bottom_right_vert.Add(self.checkbox_update, 0, wx.ALL, 2)

        sizer_bottom_horz.Add((20, 100), 0, 0, 0)

        sizer_main_vert.Add((600, 20), 0, wx.ALL, 2)

        self.text_ctrl_log = wx.TextCtrl(self.panel_main, wx.ID_ANY, "", style=wx.TE_DONTWRAP | wx.TE_MULTILINE | wx.TE_READONLY)
        sizer_main_vert.Add(self.text_ctrl_log, 1, wx.ALL | wx.EXPAND, 4)

        self.panel_status.SetSizer(sizer_status)

        self.panel_main.SetSizer(sizer_main_vert)

        self.Layout()
        self.Centre()

        # Turn on and off StayOnTop flag as a trick to raise the window to front
        self.ToggleWindowStyle(wx.STAY_ON_TOP)
        self.ToggleWindowStyle(wx.STAY_ON_TOP)

        self.initial_size = self.GetSize()
        self.tray_icon = CustomTaskBarIcon(self, icon_path)
        self.SetIcon(wx.Icon(icon_path))

        self.Bind(wx.EVT_COMBOBOX, self.OnComboboxConfig, self.combobox_config)
        self.Bind(wx.EVT_BUTTON, self.OnButtonToggleLog, self.button_log_toggle)
        self.Bind(wx.EVT_BUTTON, self.OnButtonUploadLog, self.button_log_upload)
        self.Bind(wx.EVT_BUTTON, self.OnButtonOpenInstallDir, self.button_open_install_dir)
        self.Bind(wx.EVT_BUTTON, self.OnButtonStart, self.button_start)
        self.Bind(wx.EVT_CHECKBOX, self.OnCheckboxUpdate, self.checkbox_update)
        self.Bind(wx.EVT_CLOSE, self.OnCloseFrame)

        self.text_ctrl_log.Hide()
        main_frame = self

        EVT_EXEC_FINISHED(self, self.OnExecFinished)
        EVT_LOG_UPLOADED(self, self.OnLogUploaded)
        EVT_STATUS_UPDATE(self, self.OnStatusUpdate)
        EVT_PROGRESS_UPDATE(self, self.OnProgressUpdate)
        EVT_ICONIZE_WINDOW(self, self.OnIconizeWindow)
        EVT_LOGGER_MSG(self, self.OnLoggerMsg)

        self.updater_starter = None
        self.log_uploader = None

    def OnComboboxConfig(self, event=None):
        config_manager.current_config = config_manager.compatible_configs[self.combobox_config.GetSelection()]

        no_downloads = False
        if 'no_downloads' in config_manager.current_config:
            no_downloads = config_manager.current_config['no_downloads']

        self.checkbox_update.SetValue(not no_downloads)
        self.OnCheckboxUpdate()

    def SetLogVisible(self, visible):
        if visible:
            self.text_ctrl_log.Show()
            self.SetSize(self.initial_size + (0, 250))
        else:
            self.text_ctrl_log.Hide()
            self.SetSize(self.initial_size)

    def OnButtonToggleLog(self, event):
        self.SetLogVisible(not self.text_ctrl_log.IsShown())

    def OnButtonUploadLog(self, event):
        logger.info('Log upload requested')

        self.button_log_upload.Disable()

        if not self.log_uploader:
            dlg = wx.MessageDialog(self, f'Are you sure you want to upload the log to {logs_url}? Information like hardware configuration and game install path will be available to anyone you share the resulting URL with.', 'Warning', wx.YES_NO | wx.YES_DEFAULT | wx.ICON_EXCLAMATION)
            result = dlg.ShowModal()
            dlg.Destroy()

            if result != wx.ID_YES:
                logger.info('Log upload cancelled')
                self.button_log_upload.Enable()
                return

            logger.info('Uploading, please wait...')
            # File name to save as, with the current Unix timestamp for uniqueness
            object_name = '{0}_{2}{1}'.format(*file_manager.split_extension(log_file_name) + (str(int(time.time() * 1000)),))
            self.log_uploader = LogUploaderThread(log_file_name, logs_bucket, object_name)
        else:
            logger.warning('Log upload process is already running!')

    def OnButtonOpenInstallDir(self, event):
        global logger

        data_dir = platform_manager.data_dir
        command = platform_manager.get_executable_command('file_manager')
        command.append(data_dir)
        if not process_starter.start_process(command, nowait=True): # We don't need to track the output or kill the child process on exit
            logger.error(f'Couldn\'t open the install directory: {data_dir}')

    def OnCheckboxUpdate(self, event=None):
        if self.checkbox_update.IsChecked():
            self.button_start.SetLabel('Update\n&& Start')
        else:
            self.button_start.SetLabel('Start')

    def OnButtonStart(self, event):
        global logger

        if not self.updater_starter:
            self.button_start.Disable()
            self.checkbox_update.Disable()
            self.combobox_config.Disable()

            self.updater_starter = UpdaterStarterThread(self.checkbox_update.IsChecked())
        else:
            logger.warning('Update/Start process is already running!')

    def OnCloseFrame(self, event):
        global child_process

        if child_process:
            if event.CanVeto():
                if wx.MessageBox('There is still a child process running, do you want to close it?', 'Confirm closing', wx.ICON_QUESTION | wx.YES_NO) != wx.YES:
                    event.Veto()
                    return

            child_process.terminate() # send sigterm
            #child_process.kill()      # send sigkill

        self.tray_icon.RemoveIcon()
        self.tray_icon.Destroy()
        self.Destroy()

    def OnExecFinished(self, event):
        global logger

        self.gauge_progress.SetValue(0)
        self.button_start.Enable()
        self.checkbox_update.Enable()
        self.combobox_config.Enable()

        if event.data:
            self.label_update_status.SetLabel(event.data)
            logger.error('Game process failed! Showing the logs...')

            self.Restore()
            self.SetLogVisible(True)
        else:
            self.label_update_status.SetLabel('Ready')
            logger.info('Game finished successfully! Exiting...')
            self.OnCloseFrame(self)

        self.updater_starter = None

    def OnLogUploaded(self, event):
        global logger

        self.button_log_upload.Enable()

        if event.data:
            logger.error('Log upload succeeded')
            url = event.data
            clipboard_manager.copy(url)

            dlg = wx.MessageDialog(self, f'Log was uploaded to:\n{url}\n(URL is copied to clipboard now)', 'Information', wx.OK | wx.ICON_INFORMATION)
            dlg.ShowModal()
            dlg.Destroy()
        else:
            logger.error('Log upload failed!')

        self.log_uploader = None

    def OnStatusUpdate(self, event):
        if not event.data:
            return

        self.label_update_status.SetLabel(event.data)

    def OnProgressUpdate(self, event):
        if not event.data:
            return

        if 'range' in event.data:
            self.gauge_progress.SetRange(event.data['range'])

        if 'value' in event.data:
            self.gauge_progress.SetValue(event.data['value'])

    def OnIconizeWindow(self, event):
        if not event.data:
            return

        self.tray_icon.IconizeWindow(event.data)

    def OnLoggerMsg(self, event):
        message = event.message.strip('\r')
        self.text_ctrl_log.AppendText(message+'\n')
        event.Skip()

class BARLauncher(wx.App):
    def OnInit(self):
        self.frame_launcher = LauncherFrame(None, wx.ID_ANY, "")

        logger.info('BAR Launcher started')

        #self.config_manager = ConfigManager()
        self.frame_launcher.combobox_config.Clear()
        config_names = config_manager.get_compatible_configs_names()
        if len(config_names) > 0:
            self.frame_launcher.combobox_config.Append(config_names)
            self.frame_launcher.combobox_config.SetSelection(0)
            self.frame_launcher.OnComboboxConfig()
        else:
            message = 'No configs found for {platform} platform!'.format(platform=platform_manager.current_platform)
            logger.info(message)
            self.frame_launcher.label_update_status.SetLabel(message)
            self.frame_launcher.button_start.Disable()
            self.frame_launcher.checkbox_update.Disable()

        self.SetTopWindow(self.frame_launcher)
        self.frame_launcher.Show()

        return True

if __name__ == "__main__":
    # Ugly workaround to hide a black console window on Windows (can't use "pyinstaller --noconsole" because it disables stdout completely)
    if platform.system() == 'Windows':
        if getattr(sys, 'frozen', False):
            import ctypes

            whnd = ctypes.windll.kernel32.GetConsoleWindow()
            if whnd != 0:
                ctypes.windll.user32.ShowWindow(whnd, 0)
                ctypes.windll.kernel32.CloseHandle(whnd)

    BARLauncher = BARLauncher(0)
    BARLauncher.MainLoop()
