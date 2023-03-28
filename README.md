# TW Utility: RFPM database to lua table 
It is a small utility that allow extract db tables from game `.pack` files and convert it to `.lua` script that you can `require` in your mods.

## Requirements
* OS Windows 
* Standalone option (`wh3_db_to_lua.exe`):
  * RPFM == 4.X.X (with rpfm_cli.exe and parsed db schemas)
* Direct (using sources):
  * Python 3 (I used 3.10, didn't test on older versions)
  * RPFM == 4.X.X (with rpfm_cli.exe and parsed db schemas)

## Usage

Two options: 
1. with prebuild `wh3_export_tables.exe`
2. with sources `python -m wh3_db_to_lua` (inside repository directory)

  ```
  usage: wh3_export_tables.exe [-h] -t <table_name> -r <path> -d <path> [--map-columns] [--add-return]

  options:
    -h, --help            show this help message and exit
    -t <table_name>, --table <table_name>
                          table to extract (can be added multiple times)
    -r <path>, --rpfm <path>
                          path to RPFM installation dir
    -d <path>, --dest <path>
                          destination directory where store results
    --map-columns         make rows as table<Column, Field> (by default they are table<Number, Field>)
    --add-return          add `return` statement to converted files (so you can `require` table file)
  ```

  > You can interact in the same way with package scripts if you need more detailed contol:
  >
  > 1. `python rpfm_table_extract.py`
  > ```
  >  usage: rpfm_table_extract.py [-h] -t <table_name> -r <path> -d <path>
  >
  >  options:
  >    -h, --help            show this help message and exit
  >    -t <table_name>, --table <table_name>
  >                          table to extract (can be added multiple times)
  >    -r <path>, --rpfm <path>
  >                          path to RPFM installation dir
  >    -d <path>, --dest <path>
  >                          destination directory where store results
  > ```
  > 2. `python tsv_to_lua.py`
  > ```
  > usage: tsv_to_lua.py [-h] (-f <path> | -d <path>) [--dest <path> | --replace] [--map-columns] [--add-return]
  >
  >  options:
  >    -h, --help            show this help message and exit
  >    -f <path>, --file <path>
  >                          path to .tsv file from RPFM to convert (can be added multiple times)
  >    -d <path>, --directory <path>
  >                          set directory in which to convert all .tsv to .lua
  >    --dest <path>         set different output location (default: same directory)
  >    --replace             replace original files with converted versions
  >    --map-columns         make rows as table<Column, Field> (by default they are table<Number, Field>)
  >    --add-return          add `return` statement to converted files (so you can `require` table file)
  > ```

## Building

Requirements:
* Python 3 (I used 3.10, didn't test on older versions)
* pyinstaller

Run `python build.py` inside the repository directory and you will find a new `.exe` file in the `dist/` folder

