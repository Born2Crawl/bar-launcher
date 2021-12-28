#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
import os
import wx
import json
import platform
import requests
import subprocess

class PlatformManager():
    current_platform = platform.system()
    current_dir = os.getcwd()

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
    zip_path = os.path.join(current_dir, 'bin', zip_bin)
    pr_downloader_bin = platform_binaries[current_platform]['pr_downloader']
    pr_downloader_path = os.path.join(current_dir, 'bin', pr_downloader_bin)
    spring_bin = platform_binaries[current_platform]['spring']

platform_manager = PlatformManager()

class ProcessStarter():
    def start_process(self, command):
        print(' '.join(command))
        with subprocess.Popen(command, stdout=subprocess.PIPE) as proc:
            while True:
                line = proc.stdout.readline()
                if not line:
                    break
                print(line.rstrip().decode('utf-8'))

process_starter = ProcessStarter()

class ArchiveExtractor():
    def extract_7zip(self, archive_name, destination):
        print(f'Extracting archive: "{archive_name}" "{destination}"')
        command = [platform_manager.zip_path, 'x', archive_name, '-y', f'-o{destination}']
        process_starter.start_process(command)

archive_extractor = ArchiveExtractor()

class HttpDownloader():
    def download_file(self, source_url, target_file):
        print(f'Downloading: "{source_url}" to: "{target_file}"')
        r = requests.get(source_url, allow_redirects=True)
        open(target_file, 'wb').write(r.content)

http_downloader = HttpDownloader()

class PrDownloader():
    def download_game(self, data_dir, game_name):
        command = [platform_manager.pr_downloader_path, '--filesystem-writepath', data_dir, '--download-game', game_name]
        process_starter.start_process(command)

pr_downloader = PrDownloader()

class ConfigManager():
    compatible_configs = []
    current_config = {}

    def __init__(self, *args, **kwds):
        self.compatible_configs = self.get_compatible_configs()

    def read_config(self):
        config_url = 'https://raw.githubusercontent.com/beyond-all-reason/BYAR-Chobby/master/dist_cfg/config.json'
        config_path = os.path.join(platform_manager.current_dir, 'config.json')

        if not os.path.isfile(config_path):
            print(f'Config file not found, downloading one from {config_url}')
            http_downloader.download_file(config_url, config_path)

        print(f'Reading the config file from {config_path}')
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

class UpdateManager():
    data_dir = os.path.join(platform_manager.current_dir, 'data')
    temp_archive_name = os.path.join(data_dir, 'download.7z')

    def update(self):
        setup = config_manager.current_config
        pr_downloader_games = {}
        http_resources = {}
        launchers = []

        if 'games' in setup['downloads']:
            for game in setup['downloads']['games']:
                pr_downloader_games.update({game: game})
        if 'resources' in setup['downloads']:
            for resource in setup['downloads']['resources']:
                http_resources.update({resource['url']: resource})

        for n in pr_downloader_games:
            print('================================================================================')
            pr_downloader.download_game(self.data_dir, pr_downloader_games[n])

        for n in http_resources:
            print('================================================================================')
            resource = http_resources[n]
            destination = os.path.join(self.data_dir, resource['destination'])

            if os.path.isfile(destination) or os.path.isdir(destination):
                print(f'"{destination}" already exists, skipping...')
                continue

            url = resource['url']
            is_extract = 'extract' in resource and resource['extract']

            http_downloader.download_file(url, self.temp_archive_name)

            if is_extract:
                print(f'Creating directories: "{destination}"')
                os.makedirs(destination, exist_ok=True)

                archive_extractor.extract_7zip(self.temp_archive_name, destination)

                print(f'Removing a temp file: "{self.temp_archive_name}"')
                os.remove(self.temp_archive_name)
            else:
                destination_path = os.path.dirname(destination)
                print(f'Creating directories: "{destination_path}"')
                os.makedirs(destination_path, exist_ok=True)
                print(f'Renaming a temp file: "{self.temp_archive_name}" to: "{destination}"')
                os.rename(self.temp_archive_name, destination)

    def start(self):
        setup = config_manager.current_config

        start_args = setup['launch']['start_args']
        engine = setup['launch']['engine']
        spring_path = os.path.join(self.data_dir, 'engine', engine, platform_manager.spring_bin)

        command = [spring_path, '--write-dir', self.data_dir, '--isolation']
        command.extend(start_args)
        process_starter.start_process(command)

update_manager = UpdateManager()

class LauncherFrame(wx.Frame):
    def __init__(self, *args, **kwds):
        kwds["style"] = kwds.get("style", 0) | wx.BORDER_SIMPLE | wx.CAPTION | wx.CLIP_CHILDREN | wx.CLOSE_BOX | wx.MINIMIZE_BOX | wx.SYSTEM_MENU
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

        self.combo_box_config = wx.ComboBox(self.panel_main, wx.ID_ANY, choices=[], style=wx.CB_DROPDOWN | wx.CB_READONLY)
        sizer_config.Add(self.combo_box_config, 0, 0, 0)

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

        self.Bind(wx.EVT_COMBOBOX, self.OnComboboxConfig, self.combo_box_config)
        self.Bind(wx.EVT_BUTTON, self.OnButtonToggleLog, self.button_log_toggle)
        self.Bind(wx.EVT_BUTTON, self.OnButtonUploadLog, self.button_log_update)
        self.Bind(wx.EVT_BUTTON, self.OnButtonOpenInstallDir, self.button_open_install_dir)
        self.Bind(wx.EVT_CHECKBOX, self.OnCheckboxUpdate, self.checkbox_update)
        self.Bind(wx.EVT_BUTTON, self.OnButtonStart, self.button_start)

    def OnComboboxConfig(self, event=None):
        config_manager.current_config = config_manager.compatible_configs[self.combo_box_config.GetSelection()]

        no_downloads = False
        if 'no_downloads' in config_manager.current_config:
            no_downloads = config_manager.current_config['no_downloads']

        self.checkbox_update.SetValue(not no_downloads)
        self.OnCheckboxUpdate()

        if event:
            event.Skip()

    def OnButtonToggleLog(self, event):
        print("Event handler 'OnButtonToggleLog' not implemented!")
        event.Skip()

    def OnButtonUploadLog(self, event):
        print("Event handler 'OnButtonUploadLog' not implemented!")
        event.Skip()

    def OnButtonOpenInstallDir(self, event):
        print("Event handler 'OnButtonOpenInstallDir' not implemented!")
        event.Skip()

    def OnCheckboxUpdate(self, event=None):
        if self.checkbox_update.IsChecked():
            self.button_start.SetLabel('Update')
        else:
            self.button_start.SetLabel('Start')

        if event:
            event.Skip()

    def OnButtonStart(self, event=None):
        if self.checkbox_update.IsChecked():
            update_manager.update()

        update_manager.start()

        if event:
            event.Skip()

class BARLauncher(wx.App):
    def OnInit(self):
        self.frame_launcher = LauncherFrame(None, wx.ID_ANY, "")

        #self.config_manager = ConfigManager()
        self.frame_launcher.combo_box_config.Clear()
        self.frame_launcher.combo_box_config.Append(config_manager.get_compatible_configs_names())
        self.frame_launcher.combo_box_config.SetSelection(0)
        self.frame_launcher.OnComboboxConfig()

        self.SetTopWindow(self.frame_launcher)
        self.frame_launcher.Show()
        return True

if __name__ == "__main__":
    BARLauncher = BARLauncher(0)
    BARLauncher.MainLoop()
