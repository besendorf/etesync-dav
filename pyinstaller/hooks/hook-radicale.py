from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

datas = copy_metadata("radicale") + collect_data_files("radicale")
hiddenimports = collect_submodules("radicale")
