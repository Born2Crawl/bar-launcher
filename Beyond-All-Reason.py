#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import os
import wx
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

log_file_name = 'bar-launcher.log'
logs_bucket = 'bar-infologs'
logs_url = f'https://{logs_bucket}.s3.amazonaws.com/'

event_notify_frame = None # global variable for a window to send all events to

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
        if event_notify_frame:
            wx.PostEvent(event_notify_frame, event)

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

    def get_dir_name(self, path):
        return os.path.dirname(path)

    def join_path(self, *args):
        return os.path.join(*args)

    def split_extension(self, path):
        return os.path.splitext(path)

    def extract_filename(self, path):
        return os.path.basename(path)

    def file_exists(self, path):
        return os.path.isfile(path)

    def dir_exists(self, path):
        return os.path.isdir(path)

    def make_dirs(self, path):
        return os.makedirs(path, exist_ok=True)

    def rename(self, current_path, new_path):
        global logger

        try:
            return os.rename(current_path, new_path)
        except:
            logger.error('Couldn\'t rename!')
            e = sys.exc_info()[1]
            logger.error(e)

    def remove(self, path):
        global logger

        try:
            return os.remove(path)
        except:
            logger.error('Couldn\'t remove!')
            e = sys.exc_info()[1]
            logger.error(e)

file_manager = FileManager()

class PlatformManager():
    current_platform = platform.system()
    current_dir = file_manager.get_current_dir()
    data_dir = file_manager.join_path(current_dir, 'data')
    executable_dir = file_manager.join_path(current_dir, 'bin')

    config_files = {
        'launcher': {
            'url': 'https://raw.githubusercontent.com/beyond-all-reason/BYAR-Chobby/master/dist_cfg/config.json',
            'path': file_manager.join_path(current_dir, 'config.json'),
        },
        'lobby': {
            'url': 'https://raw.githubusercontent.com/beyond-all-reason/BYAR-Chobby/master/dist_cfg/files/chobby_config.json',
            'path': file_manager.join_path(data_dir, 'chobby_config.json'),
        },
    }

    def get_config_path(self, name):
        return self.config_files[name]['path']

    def get_config_url(self, name):
        return self.config_files[name]['url']

    def download_config(self, name):
        config_path = self.get_config_path(name)
        config_url = self.get_config_url(name)

        logger.info(f'Trying to download a fresh {name} config from {config_url}')
        http_downloader.download_file(config_url, config_path)

    platform_binaries = {
        'Windows': {
            '7zip': {
                'command': ['7z_win64.exe'],
                'path': 'bin',
                'downloads': [
                    'https://github.com/Born2Crawl/bar-launcher/raw/main/bin/7z_win64.exe'
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
                    'https://github.com/Born2Crawl/bar-launcher/raw/main/bin/7zz_linux_x86-64'
                ],
            },
            'pr_downloader': {
                'command': ['pr-downloader'],
                'path': 'bin',
                'downloads': [
                    'https://github.com/Born2Crawl/bar-launcher/raw/main/bin/pr-downloader'
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
                    'https://github.com/Born2Crawl/bar-launcher/raw/main/bin/7zz_macos'
                ],
            },
            'pr_downloader': {
                'command': ['pr-downloader-mac'],
                'path': 'bin',
                'downloads': [
                    'https://github.com/Born2Crawl/bar-launcher/raw/main/bin/pr-downloader-mac'
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
    def start_process(self, command):
        global event_notify_frame
        global logger

        logger.info('Starting a process:')
        logger.info(' '.join(command))
        try:
            with subprocess.Popen(command, stdout=subprocess.PIPE) as proc:
                while True:
                    line = proc.stdout.readline()
                    if not line:
                        break
                    if len(line.rstrip()) > 0:
                        logger.info(line.rstrip().decode('utf-8'))
        except:
            logger.error('Process start failed!')
            e = sys.exc_info()[1]
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

            r = requests.get(source_url, allow_redirects=True)
            open(target_file, 'wb').write(r.content)
        except:
            logger.error('Download failed:')
            e = sys.exc_info()[1]
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
        global event_notify_frame
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

            wx.PostEvent(event_notify_frame, LogUploadedEvent(result))
        except:
            logger.error('Upload failed!')
            e = sys.exc_info()[1]
            logger.error(e)

            wx.PostEvent(event_notify_frame, LogUploadedEvent(None))

class ClipboardManager():
    def copy(self, text):
        global logger

        try:
            logger.info(f'Copying to clipboard: "{text}"')
            pyperclip.copy(text)
        except:
            logger.error('Copying failed:')
            e = sys.exc_info()[1]
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

        platform_manager.download_config('launcher')
        launcher_config_path = platform_manager.get_config_path('launcher')
        if not file_manager.file_exists(launcher_config_path):
            raise Exception('Couldn\'t find the config file to use!')

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
        global event_notify_frame
        global logger

        config = config_manager.current_config

        try:
            if self.is_update:
                pr_downloader_games = {}
                http_resources = {}
                launchers = []

                # Updating the game according to the current config
                if 'games' in config['downloads']:
                    for game in config['downloads']['games']:
                        pr_downloader_games.update({game: game})

                if 'resources' in config['downloads']:
                    for resource in config['downloads']['resources']:
                        http_resources.update({resource['url']: resource})

                logger.info('Step 1: Downloading the game repositories')
                for n in pr_downloader_games:
                    logger.info('================================================================================')
                    if not pr_downloader.download_game(self.data_dir, pr_downloader_games[n]):
                        raise Exception(f'Error updating {n}!')

                logger.info('Step 2: Downloading the engine and additional resources')
                for n in http_resources:
                    logger.info('================================================================================')
                    resource = http_resources[n]
                    destination = file_manager.join_path(self.data_dir, resource['destination'])

                    if file_manager.file_exists(destination) or file_manager.dir_exists(destination):
                        logger.warning(f'"{destination}" already exists, skipping...')
                        continue

                    url = resource['url']
                    is_extract = 'extract' in resource and resource['extract']

                    if not http_downloader.download_file(url, self.temp_archive_name):
                        raise Exception(f'Error downloading: {url}!')

                    if is_extract:
                        if file_manager.file_exists(self.temp_archive_name):
                            logger.info(f'Creating directories: "{destination}"')
                            file_manager.make_dirs(destination)

                            if not archive_extractor.extract_7zip(self.temp_archive_name, destination):
                                raise Exception(f'Error extracting {self.temp_archive_name}!')

                            logger.info(f'Removing a temp file: "{self.temp_archive_name}"')
                            file_manager.remove(self.temp_archive_name)
                        else:
                            logger.info('Downloaded file didn\'t exist!')
                    else:
                        if file_manager.file_exists(self.temp_archive_name):
                            destination_path = file_manager.get_dir_name(destination)
                            logger.info(f'Creating directories: "{destination_path}"')
                            file_manager.make_dirs(destination_path)

                            logger.info(f'Renaming a temp file: "{self.temp_archive_name}" to: "{destination}"')
                            file_manager.rename(self.temp_archive_name, destination)
                        else:
                            logger.info('Downloaded file didn\'t exist!')

            logger.info('Step 3: Downloading the lobby config')
            platform_manager.download_config('lobby')
            lobby_config_path = platform_manager.get_config_path('lobby')
            if not file_manager.file_exists(lobby_config_path):
                raise Exception('Couldn\'t find the config file to use!')

            logger.info('Step 4: Starting the game')
            # Starting the game
            start_args = config['launch']['start_args']
            engine = config['launch']['engine']
            spring_command = platform_manager.get_executable_command('spring')
            spring_command[0] = file_manager.join_path(self.data_dir, 'engine', engine, spring_command[0])
            spring_command.extend(['--write-dir', self.data_dir, '--isolation'])
            spring_command.extend(start_args)
            if not process_starter.start_process(spring_command):
                raise Exception('Error starting the game!')

            logger.info('Process finished!')
            wx.PostEvent(event_notify_frame, ExecFinishedEvent(True))
        except:
            logger.error('Error while updating/starting:')
            e = sys.exc_info()[1]
            logger.error(e)
            wx.PostEvent(event_notify_frame, ExecFinishedEvent(False))

class LauncherFrame(wx.Frame):

    def __init__(self, *args, **kwds):
        global event_notify_frame

        kwds["style"] = kwds.get("style", 0) | wx.CAPTION | wx.CLIP_CHILDREN | wx.CLOSE_BOX | wx.MINIMIZE_BOX | wx.SYSTEM_MENU
        wx.Frame.__init__(self, *args, **kwds)
        self.SetSize((700, 250))
        self.SetTitle("Beyond All Reason")

        self.panel_main = wx.Panel(self, wx.ID_ANY)

        sizer_main_vert = wx.BoxSizer(wx.VERTICAL)

        sizer_top_horz = wx.BoxSizer(wx.HORIZONTAL)
        sizer_main_vert.Add(sizer_top_horz, 0, wx.ALL | wx.EXPAND, 4)

        sizer_title = wx.BoxSizer(wx.VERTICAL)
        sizer_top_horz.Add(sizer_title, 1, wx.EXPAND, 0)

        label_title = wx.StaticText(self.panel_main, wx.ID_ANY, "Beyond All Reason")
        label_title.SetFont(wx.Font(24, wx.FONTFAMILY_SCRIPT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, 0, ""))
        sizer_title.Add(label_title, 0, wx.ALL, 4)

        sizer_top_horz.Add((20, 80), 1, wx.ALL | wx.EXPAND, 2)

        sizer_config = wx.BoxSizer(wx.VERTICAL)
        sizer_top_horz.Add(sizer_config, 0, wx.EXPAND, 0)

        label_config = wx.StaticText(self.panel_main, wx.ID_ANY, "Config:")
        sizer_config.Add(label_config, 0, wx.ALL, 2)

        self.combobox_config = wx.ComboBox(self.panel_main, wx.ID_ANY, choices=[], style=wx.CB_DROPDOWN | wx.CB_READONLY)
        sizer_config.Add(self.combobox_config, 0, wx.ALL, 2)

        sizer_bottom_horz = wx.BoxSizer(wx.HORIZONTAL)
        sizer_main_vert.Add(sizer_bottom_horz, 0, wx.ALL | wx.EXPAND, 4)

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

        self.label_update_status = wx.StaticText(self.panel_main, wx.ID_ANY, "Ready")
        sizer_bottom_left_vert.Add(self.label_update_status, 0, wx.ALL, 2)

        self.gauge_update_current = wx.Gauge(self.panel_main, wx.ID_ANY, 10)
        self.gauge_update_current.SetMinSize((550, 15))
        sizer_bottom_left_vert.Add(self.gauge_update_current, 0, wx.ALL | wx.EXPAND, 2)

        self.gauge_update_total = wx.Gauge(self.panel_main, wx.ID_ANY, 10)
        sizer_bottom_left_vert.Add(self.gauge_update_total, 0, wx.ALL | wx.EXPAND, 2)

        sizer_bottom_horz.Add((20, 80), 0, wx.ALL, 2)

        sizer_bottom_right_vert = wx.BoxSizer(wx.VERTICAL)
        sizer_bottom_horz.Add(sizer_bottom_right_vert, 0, 0, 0)

        self.button_start = wx.Button(self.panel_main, wx.ID_ANY, "Start")
        self.button_start.SetMinSize((120, 60))
        self.button_start.SetFont(wx.Font(14, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, 0, ""))
        sizer_bottom_right_vert.Add(self.button_start, 0, wx.ALL, 2)

        self.checkbox_update = wx.CheckBox(self.panel_main, wx.ID_ANY, "Update")
        sizer_bottom_right_vert.Add(self.checkbox_update, 0, wx.ALL, 2)

        sizer_main_vert.Add((80, 10), 0, wx.ALL, 2)

        self.text_ctrl_log = wx.TextCtrl(self.panel_main, wx.ID_ANY, "", style=wx.TE_DONTWRAP | wx.TE_MULTILINE | wx.TE_READONLY)
        sizer_main_vert.Add(self.text_ctrl_log, 1, wx.ALL | wx.EXPAND, 4)

        self.panel_main.SetSizer(sizer_main_vert)

        self.Layout()
        self.Centre()
        #self.Restore()
        #self.Raise()

        self.Bind(wx.EVT_COMBOBOX, self.OnComboboxConfig, self.combobox_config)
        self.Bind(wx.EVT_BUTTON, self.OnButtonToggleLog, self.button_log_toggle)
        self.Bind(wx.EVT_BUTTON, self.OnButtonUploadLog, self.button_log_upload)
        self.Bind(wx.EVT_BUTTON, self.OnButtonOpenInstallDir, self.button_open_install_dir)
        self.Bind(wx.EVT_BUTTON, self.OnButtonStart, self.button_start)
        self.Bind(wx.EVT_CHECKBOX, self.OnCheckboxUpdate, self.checkbox_update)

        self.text_ctrl_log.Hide()
        event_notify_frame = self

        EVT_EXEC_FINISHED(self, self.OnExecFinished)
        EVT_LOG_UPLOADED(self, self.OnLogUploaded)
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

    def OnButtonToggleLog(self, event):
        if self.text_ctrl_log.IsShown():
            self.text_ctrl_log.Hide()
            self.SetSize((700, 250))
        else:
            self.text_ctrl_log.Show()
            self.SetSize((700, 500))

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
        if not process_starter.start_process(command):
            logger.error(f'Couldn\'t open the install directory: {data_dir}')

    def OnCheckboxUpdate(self, event=None):
        if self.checkbox_update.IsChecked():
            self.button_start.SetLabel('Update')
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

    def OnExecFinished(self, event):
        global logger

        self.label_update_status.SetLabel('Ready')
        self.button_start.Enable()
        self.checkbox_update.Enable()
        self.combobox_config.Enable()

        if event.data:
            logger.info('Game finished successfully!')
        else:
            logger.error('Game process failed!')

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

    def OnLoggerMsg(self, event):
        message = event.message.strip('\r')
        if message.startswith('Step'):
            self.label_update_status.SetLabel(message)
        self.text_ctrl_log.AppendText(message+'\n')
        event.Skip()

class BARLauncher(wx.App):
    def OnInit(self):
        self.frame_launcher = LauncherFrame(None, wx.ID_ANY, "")

        #self.config_manager = ConfigManager()
        self.frame_launcher.combobox_config.Clear()
        self.frame_launcher.combobox_config.Append(config_manager.get_compatible_configs_names())
        self.frame_launcher.combobox_config.SetSelection(0)
        self.frame_launcher.OnComboboxConfig()

        self.SetTopWindow(self.frame_launcher)
        self.frame_launcher.Show()

        logger.info('BAR Launcher started')

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
