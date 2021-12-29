#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import os
import wx
import sys
import json
import logging
import platform
import requests
import subprocess
from threading import *

# Cutons events to notify about Update/Start execution finished and logging output
event_notify_frame = None
EVT_EXEC_FINISHED_ID = wx.NewIdRef(count=1)
EVT_LOG_LINE_ID = wx.NewIdRef(count=1)

def EVT_EXEC_FINISHED(win, func):
    win.Connect(-1, -1, EVT_EXEC_FINISHED_ID, func)

def EVT_LOG_LINE(win, func):
    win.Connect(-1, -1, EVT_LOG_LINE_ID, func)

class ExecFinishedEvent(wx.PyEvent):
    def __init__(self, data):
        wx.PyEvent.__init__(self)
        self.SetEventType(EVT_EXEC_FINISHED_ID)
        self.data = data

class LogLineEvent(wx.PyEvent):
    def __init__(self, data):
        wx.PyEvent.__init__(self)
        self.SetEventType(EVT_LOG_LINE_ID)
        self.data = data

class FileManager():
    def get_current_dir(self):
        return os.getcwd()

    def get_dir_name(self, path):
        return os.path.dirname(path)

    def join_path(self, *args):
        return os.path.join(*args)

    def file_exists(self, path):
        return os.path.isfile(path)

    def dir_exists(self, path):
        return os.path.isdir(path)

    def make_dirs(self, path):
        return os.makedirs(path, exist_ok=True)

    def rename(self, current_path, new_path):
        try:
            return os.rename(current_path, new_path)
        except:
            logging.error('Couldn\'t rename!')
            e = sys.exc_info()[1]
            logging.error(e)

    def remove(self, path):
        try:
            return os.remove(path)
        except:
            logging.error('Couldn\'t remove!')
            e = sys.exc_info()[1]
            logging.error(e)

file_manager = FileManager()

class PlatformManager():
    current_platform = platform.system()
    current_dir = file_manager.get_current_dir()

    platform_binaries = {
        'Windows': {
            '7zip': '7z_win64.exe',
            'pr_downloader': 'pr-downloader.exe',
            'spring': 'spring.exe',
        },
        'Linux': {
            '7zip': '7zz_linux_x86-64',
            'pr_downloader': 'pr-downloader',
            'spring': 'spring',
        },
        'Darwin': {
            '7zip': '7zz_macos',
            'pr_downloader': 'pr-downloader-mac',
            'spring': 'spring',
        },
    }

    zip_bin = platform_binaries[current_platform]['7zip']
    zip_path = file_manager.join_path(current_dir, 'bin', zip_bin)
    pr_downloader_bin = platform_binaries[current_platform]['pr_downloader']
    pr_downloader_path = file_manager.join_path(current_dir, 'bin', pr_downloader_bin)
    spring_bin = platform_binaries[current_platform]['spring']

platform_manager = PlatformManager()

class ProcessStarter():
    def start_process(self, command):
        global event_notify_frame

        logging.info('Starting a process:')
        logging.info(' '.join(command))
        try:
            with subprocess.Popen(command, stdout=subprocess.PIPE) as proc:
                while True:
                    line = proc.stdout.readline()
                    if not line:
                        break
                    wx.PostEvent(event_notify_frame, LogLineEvent(line.rstrip().decode('utf-8')))
            return True
        except:
            logging.error('Process start failed!')
            e = sys.exc_info()[1]
            logging.error(e)
            return False

process_starter = ProcessStarter()

class ArchiveExtractor():
    def extract_7zip(self, archive_name, destination):
        logging.info(f'Extracting archive: "{archive_name}" "{destination}"')
        command = [platform_manager.zip_path, 'x', archive_name, '-y', f'-o{destination}']
        return process_starter.start_process(command)

archive_extractor = ArchiveExtractor()

class HttpDownloader():
    def download_file(self, source_url, target_file):
        logging.info(f'Downloading: "{source_url}" to: "{target_file}"')
        try:
            r = requests.get(source_url, allow_redirects=True)
            open(target_file, 'wb').write(r.content)
        except:
            logging.error('Download failed:')
            e = sys.exc_info()[1]
            logging.error(e)
            return False

        return True

http_downloader = HttpDownloader()

class PrDownloader():
    def download_game(self, data_dir, game_name):
        command = [platform_manager.pr_downloader_path, '--filesystem-writepath', data_dir, '--download-game', game_name]
        return process_starter.start_process(command)

pr_downloader = PrDownloader()

class ConfigManager():
    compatible_configs = []
    current_config = {}

    def __init__(self, *args, **kwds):
        self.compatible_configs = self.get_compatible_configs()

    def read_config(self):
        config_url = 'https://raw.githubusercontent.com/beyond-all-reason/BYAR-Chobby/master/dist_cfg/config.json'
        config_path = file_manager.join_path(platform_manager.current_dir, 'config.json')

        if not file_manager.file_exists(config_path):
            logging.info(f'Config file not found, downloading one from {config_url}')
            http_downloader.download_file(config_url, config_path)

        logging.info(f'Reading the config file from {config_path}')
        f = open(config_path)
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
    data_dir = file_manager.join_path(platform_manager.current_dir, 'data')
    temp_archive_name = file_manager.join_path(data_dir, 'download.7z')

    def __init__(self, is_update):
        Thread.__init__(self)
        self.is_update = is_update
        self.start()

    def run(self):
        global event_notify_frame

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

                for n in pr_downloader_games:
                    logging.info('================================================================================')
                    if not pr_downloader.download_game(self.data_dir, pr_downloader_games[n]):
                        raise Exception(f'Error updating {n}!')

                for n in http_resources:
                    logging.info('================================================================================')
                    resource = http_resources[n]
                    destination = file_manager.join_path(self.data_dir, resource['destination'])

                    if file_manager.file_exists(destination) or file_manager.dir_exists(destination):
                        logging.warning(f'"{destination}" already exists, skipping...')
                        continue

                    url = resource['url']
                    is_extract = 'extract' in resource and resource['extract']

                    if not http_downloader.download_file(url, self.temp_archive_name):
                        raise Exception(f'Error downloading: {url}!')

                    if is_extract:
                        if file_manager.file_exists(self.temp_archive_name):
                            logging.info(f'Creating directories: "{destination}"')
                            file_manager.make_dirs(destination)

                            if not archive_extractor.extract_7zip(self.temp_archive_name, destination):
                                raise Exception(f'Error extracting {self.temp_archive_name}!')

                            logging.info(f'Removing a temp file: "{self.temp_archive_name}"')
                            file_manager.remove(self.temp_archive_name)
                        else:
                            logging.info('Downloaded file didn\'t exist!')
                    else:
                        if file_manager.file_exists(self.temp_archive_name):
                            destination_path = file_manager.get_dir_name(destination)
                            logging.info(f'Creating directories: "{destination_path}"')
                            file_manager.make_dirs(destination_path)

                            logging.info(f'Renaming a temp file: "{self.temp_archive_name}" to: "{destination}"')
                            file_manager.rename(self.temp_archive_name, destination)
                        else:
                            logging.info('Downloaded file didn\'t exist!')

            # Starting the game
            start_args = config['launch']['start_args']
            engine = config['launch']['engine']
            spring_path = file_manager.join_path(self.data_dir, 'engine', engine, platform_manager.spring_bin)

            command = [spring_path, '--write-dir', self.data_dir, '--isolation']
            command.extend(start_args)
            if not process_starter.start_process(command):
                raise Exception('Error starting the game!')

            wx.PostEvent(event_notify_frame, ExecFinishedEvent(True))
        except:
            logging.error('Error while updating/starting:')
            e = sys.exc_info()[1]
            logging.error(e)
            wx.PostEvent(event_notify_frame, ExecFinishedEvent(False))

class LauncherFrame(wx.Frame):

    def __init__(self, *args, **kwds):
        global event_notify_frame

        kwds["style"] = kwds.get("style", 0) | wx.CAPTION | wx.CLIP_CHILDREN | wx.CLOSE_BOX | wx.MINIMIZE_BOX | wx.SYSTEM_MENU
        wx.Frame.__init__(self, *args, **kwds)
        self.SetSize((703, 326))
        self.SetTitle("Beyond All Reason")

        self.panel_main = wx.Panel(self, wx.ID_ANY)

        sizer_main_vert = wx.BoxSizer(wx.VERTICAL)

        sizer_top_horz = wx.BoxSizer(wx.HORIZONTAL)
        sizer_main_vert.Add(sizer_top_horz, 1, wx.EXPAND, 0)

        label_title = wx.StaticText(self.panel_main, wx.ID_ANY, "Beyond All Reason")
        label_title.SetFont(wx.Font(20, wx.FONTFAMILY_MODERN, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, 0, ""))
        sizer_top_horz.Add(label_title, 0, 0, 0)

        sizer_top_horz.Add((290, 20), 0, 0, 0)

        sizer_config = wx.BoxSizer(wx.VERTICAL)
        sizer_top_horz.Add(sizer_config, 1, wx.EXPAND, 0)

        label_config = wx.StaticText(self.panel_main, wx.ID_ANY, "Config:")
        sizer_config.Add(label_config, 0, 0, 0)

        self.combobox_config = wx.ComboBox(self.panel_main, wx.ID_ANY, choices=[], style=wx.CB_DROPDOWN | wx.CB_READONLY)
        sizer_config.Add(self.combobox_config, 0, 0, 0)

        sizer_bottom_horz = wx.BoxSizer(wx.HORIZONTAL)
        sizer_main_vert.Add(sizer_bottom_horz, 1, wx.EXPAND, 0)

        sizer_bottom_left_vert = wx.BoxSizer(wx.VERTICAL)
        sizer_bottom_horz.Add(sizer_bottom_left_vert, 1, wx.EXPAND, 0)

        sizer_log_buttonz_horz = wx.BoxSizer(wx.HORIZONTAL)
        sizer_bottom_left_vert.Add(sizer_log_buttonz_horz, 1, wx.EXPAND, 0)

        self.button_log_toggle = wx.Button(self.panel_main, wx.ID_ANY, "Toggle Log")
        sizer_log_buttonz_horz.Add(self.button_log_toggle, 0, 0, 0)

        self.button_log_update = wx.Button(self.panel_main, wx.ID_ANY, "Upload Log")
        sizer_log_buttonz_horz.Add(self.button_log_update, 0, 0, 0)

        self.button_open_install_dir = wx.Button(self.panel_main, wx.ID_ANY, "Open Install Directory")
        sizer_log_buttonz_horz.Add(self.button_open_install_dir, 0, 0, 0)

        label_update_status = wx.StaticText(self.panel_main, wx.ID_ANY, "Status")
        sizer_bottom_left_vert.Add(label_update_status, 0, 0, 0)

        self.gauge_update_current = wx.Gauge(self.panel_main, wx.ID_ANY, 10)
        self.gauge_update_current.SetMinSize((550, 15))
        sizer_bottom_left_vert.Add(self.gauge_update_current, 0, wx.EXPAND, 0)

        self.gauge_update_total = wx.Gauge(self.panel_main, wx.ID_ANY, 10)
        sizer_bottom_left_vert.Add(self.gauge_update_total, 0, wx.EXPAND, 0)

        sizer_bottom_left_vert.Add((20, 20), 0, 0, 0)

        sizer_bottom_right_vert = wx.BoxSizer(wx.VERTICAL)
        sizer_bottom_horz.Add(sizer_bottom_right_vert, 1, wx.EXPAND, 0)

        self.button_start = wx.Button(self.panel_main, wx.ID_ANY, "Start")
        self.button_start.SetMinSize((120, 60))
        self.button_start.SetFont(wx.Font(14, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, 0, ""))
        sizer_bottom_right_vert.Add(self.button_start, 0, 0, 0)

        self.checkbox_update = wx.CheckBox(self.panel_main, wx.ID_ANY, "Update")
        sizer_bottom_right_vert.Add(self.checkbox_update, 0, 0, 0)

        self.panel_main.SetSizer(sizer_main_vert)

        self.Layout()
        self.Centre()

        self.Bind(wx.EVT_COMBOBOX, self.OnComboboxConfig, self.combobox_config)
        self.Bind(wx.EVT_BUTTON, self.OnButtonToggleLog, self.button_log_toggle)
        self.Bind(wx.EVT_BUTTON, self.OnButtonUploadLog, self.button_log_update)
        self.Bind(wx.EVT_BUTTON, self.OnButtonOpenInstallDir, self.button_open_install_dir)
        self.Bind(wx.EVT_CHECKBOX, self.OnCheckboxUpdate, self.checkbox_update)
        self.Bind(wx.EVT_BUTTON, self.OnButtonStart, self.button_start)

        event_notify_frame = self

        EVT_EXEC_FINISHED(self, self.OnExecFinished)
        EVT_LOG_LINE(self, self.OnLogLine)

        self.updater_starter = None

    def OnComboboxConfig(self, event=None):
        config_manager.current_config = config_manager.compatible_configs[self.combobox_config.GetSelection()]

        no_downloads = False
        if 'no_downloads' in config_manager.current_config:
            no_downloads = config_manager.current_config['no_downloads']

        self.checkbox_update.SetValue(not no_downloads)
        self.OnCheckboxUpdate()

        if event:
            event.Skip()

    def OnButtonToggleLog(self, event):
        logging.info("Event handler 'OnButtonToggleLog' not implemented!")
        event.Skip()

    def OnButtonUploadLog(self, event):
        logging.info("Event handler 'OnButtonUploadLog' not implemented!")
        event.Skip()

    def OnButtonOpenInstallDir(self, event):
        logging.info("Event handler 'OnButtonOpenInstallDir' not implemented!")
        event.Skip()

    def OnCheckboxUpdate(self, event=None):
        if self.checkbox_update.IsChecked():
            self.button_start.SetLabel('Update')
        else:
            self.button_start.SetLabel('Start')

        if event:
            event.Skip()

    def OnButtonStart(self, event):
        global event_notify_frame

        if not self.updater_starter:
            self.button_start.Disable()
            self.checkbox_update.Disable()
            self.combobox_config.Disable()

            self.updater_starter = UpdaterStarterThread(self.checkbox_update.IsChecked())
        else:
            logging.warning('Update/Start process is already running!')

        event.Skip()

    def OnExecFinished(self, event):
        self.button_start.Enable()
        self.checkbox_update.Enable()
        self.combobox_config.Enable()

        if event.data:
            logging.info('Start success!')
        else:
            logging.error('Start failed!')

        self.updater_starter = None

    def OnLogLine(self, event):
        if event.data:
            logging.info(event.data)

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
        return True

if __name__ == "__main__":
    logging.basicConfig(filename='bar-launcher.log', encoding='utf-8', level=logging.DEBUG)
    logging.getLogger().setLevel(logging.DEBUG)

    BARLauncher = BARLauncher(0)
    BARLauncher.MainLoop()
