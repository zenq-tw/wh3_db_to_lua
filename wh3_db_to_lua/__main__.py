import argparse
import sys
import tempfile
from pathlib import Path
from pprint import pprint

from wh3_db_to_lua import rpfm_table_extract, tsv_to_lua


is_exe = getattr(sys, 'frozen', False)




def _init_cli() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(
        prog='wh3_export_tables.exe' if is_exe else 'python -m wh3_db_to_lua',
        description='WH3 utility for exporting database tables as lua scripts using RPFM CLI',
    )

    cli.add_argument(
        '-t', '--table',
        action='append',
        required=True,
        metavar='<table_name>',
        type=rpfm_table_extract.normalized_table_name,
        help='table to extract (can be added multiple times)',
    )

    cli.add_argument(
        '-r', '--rpfm',
        required=True,
        metavar='<path>',
        type=rpfm_table_extract.check_existence_and_return_path_obj,
        help='path to RPFM installation dir',
    )

    cli.add_argument(
        '-d', '--dest',
        required=True,
        metavar='<path>',
        type=rpfm_table_extract.check_existence_and_return_path_obj,
        help='destination directory where store results',
    )

    cli.add_argument(
        '--map-columns',
        action='store_true',
        help='make rows as table<Column, Field> (by default they are table<Number, Field>)',
    )

    cli.add_argument(
        '--add-return',
        action='store_true',
        help='add `return` statement to converted files (so you can `require` table file)',
    )

    cli.add_argument(
        '--md5',
        action='store_true',
        help='calculate md5_checksum. WARNING: this will lead to different output table structure',
    )

    return cli



args = _init_cli().parse_args()


print('=====================================')
print('-- Tables to extract (normalized): --')
pprint(args.table)

with tempfile.TemporaryDirectory() as tmpdir_path:
    tmpdir = Path(tmpdir_path)

    print('-------------------------------------')

    files = rpfm_table_extract.execute(
        rpfm_path=args.rpfm,
        table_names=args.table,
        dest=tmpdir,
    )
    print('------------ Extracted --------------')

    tsv_to_lua.execute(
        files,
        dest=args.dest,
        should_replace=True,
        map_columns=args.map_columns,
        add_return=args.add_return,
        calculate_md5=args.md5,
    )

    print('------------ Converted --------------')

print('-------------- Done -----------------')
