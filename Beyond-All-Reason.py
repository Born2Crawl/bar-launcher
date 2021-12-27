import os
import sys
import json
import platform
import requests
import subprocess

current_platform = platform.system()
current_dir = os.getcwd()
data_dir = os.path.join(current_dir, 'data')
is_dev = len(sys.argv) > 1 and str(sys.argv[1]) == 'dev'

config_url = 'https://raw.githubusercontent.com/beyond-all-reason/BYAR-Chobby/master/dist_cfg/config.json'
config_path = os.path.join(current_dir, 'config.json')

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

temp_archive_name = os.path.join(data_dir, 'download.7z')

def start_process(command):
    print(' '.join(command))
    with subprocess.Popen(command, stdout=subprocess.PIPE) as proc:
        while True:
            line = proc.stdout.readline()
            if not line:
                break
            print(line.rstrip().decode('utf-8'))

def download_file(source_url, target_file):
    r = requests.get(source_url, allow_redirects=True)
    open(target_file, 'wb').write(r.content)

def read_config():
    if not os.path.isfile(config_path):
        print(f'Config file not found, downloading one from {config_url}')
        download_file(config_url, config_path)

    print(f'Reading the config file from {config_path}')
    f = open(config_path)
    data = json.load(f)
    f.close()
    return data

def main():
    data = read_config()

    if not 'setups' in data:
        raise Exception('Not a valid config file, missing "setups" section!')

    pr_downloader_games = {}
    http_resources = {}
    launchers = []

    for setup in data['setups']:
        if not 'package' in setup or not 'platform' in setup['package'] or not 'launch' in setup:
            raise Exception('Not a valid config setup, missing "package->platform" or "launch" section!')

        if ((setup['package']['platform'] == 'win32' and current_platform == 'Windows') \
                    or (setup['package']['platform'] == 'linux' and current_platform == 'Linux') \
                    or (setup['package']['platform'] == 'darwin' and current_platform == 'Darwin')) \
                and (is_dev == setup['package']['id'].startswith('dev-')):

            if 'games' in setup['downloads']:
                for game in setup['downloads']['games']:
                    pr_downloader_games.update({game: game})
            if 'resources' in setup['downloads']:
                for resource in setup['downloads']['resources']:
                    http_resources.update({resource['url']: resource})

            launchers.append(setup['launch'])

    for n in pr_downloader_games:
        print('================================================================================')
        pr_downloader_game = pr_downloader_games[n]
        pr_downloader_path = os.path.join(current_dir, 'bin', pr_downloader_bin)

        command = [pr_downloader_path, '--filesystem-writepath', data_dir, '--download-game', pr_downloader_game]
        start_process(command)

    for n in http_resources:
        print('================================================================================')
        resource = http_resources[n]
        destination = os.path.join(data_dir, resource['destination'])

        if os.path.isfile(destination) or os.path.isdir(destination):
            print(f'"{destination}" already exists, skipping...')
            continue

        url = resource['url']
        is_extract = 'extract' in resource and resource['extract']

        print(f'Downloading: "{url}" to: "{temp_archive_name}"')
        download_file(url, temp_archive_name)

        if is_extract:
            print(f'Creating directories: "{destination}"')
            os.makedirs(destination, exist_ok=True)
            print(f'Extracting an archive: "{temp_archive_name}" "{destination}"')

            command = [zip_path, 'x', temp_archive_name, '-y', f'-o{destination}']
            start_process(command)

            print(f'Removing a temp file: "{temp_archive_name}"')
            os.remove(temp_archive_name)
        else:
            destination_path = os.path.dirname(destination)
            print(f'Creating directories: "{destination_path}"')
            os.makedirs(destination_path, exist_ok=True)
            print(f'Renaming a temp file: "{temp_archive_name}" to: "{destination}"')
            os.rename(temp_archive_name, destination)

    if len(launchers) > 0:
        start_args = launchers[0]['start_args']
        engine = launchers[0]['engine']
        spring_path = os.path.join(data_dir, 'engine', engine, spring_bin)

        command = [spring_path, '--write-dir', data_dir, '--isolation']
        command.extend(start_args)
        start_process(command)

if __name__ == '__main__':
    main()
