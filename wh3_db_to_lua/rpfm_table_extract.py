import argparse
import os
import shutil
import subprocess
import tempfile
import winreg
from pathlib import Path
from pprint import pprint
from typing import NamedTuple



class RPFMDependencies(NamedTuple):
    cli: Path
    schema: Path
    pack: Path



def _get_game_data_dir() -> Path:
    try:
        hkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\Wow6432Node\Valve\Steam")
    except Exception:
        raise RuntimeError('Failed to get Steam installation directory') from None

    try:
        path, _ = winreg.QueryValueEx(hkey, "InstallPath")
    except Exception:
        raise RuntimeError('Failed to get Steam installation directory') from None

    path = Path(path)
    assert path.exists(), 'Failed to get Steam installation directory'
    
    path = path / 'steamapps/common/Total War WARHAMMER III/data'
    assert path.exists(), f'Failed to get WH3 data folder: {path}'

    return path



def _get_rpfm_wh3_schema() -> Path:
    path = Path(os.getenv('APPDATA')) / 'rpfm/config/schemas/schema_wh3.ron'
    assert path.exists(), f'Failed to get RPFM schemas directory. Expected to found it here: {path}'

    return path


def _get_rpfm_cli_path(rpfm_dir: Path) -> Path:
    path = rpfm_dir / 'rpfm_cli.exe'
    assert path.exists(), f'Failed to get "rpfm_cli.exe". Expected to found it here: {path}'

    return path


def _get_rpfm_dependency_paths(rpfm_path: Path) -> RPFMDependencies:
    pack_file = _get_game_data_dir() / 'data.pack'
    assert pack_file.exists(), f'Failed to find "data.pack" inside game data directory: {pack_file}'

    return RPFMDependencies(
        cli=_get_rpfm_cli_path(rpfm_path),
        schema=_get_rpfm_wh3_schema(),
        pack=pack_file,
    )


def _extract_tables(rpfm: RPFMDependencies, table_names: list[str], destination_dir_path: Path) -> list[Path]:
    with tempfile.TemporaryDirectory() as tmpdir_path:
        file_args = ' '.join(
            f'--file-path db/{tname}_tables/data__;{tmpdir_path}'
            for tname in table_names
        )

        command = ' '.join([
            str(rpfm.cli),
            '--game warhammer_3',
            'pack',
            'extract',
           f'--pack-path "{rpfm.pack}"',
           f'--tables-as-tsv "{rpfm.schema}"',
            file_args,
        ])

        results = subprocess.run(command, shell=True)
        results.check_returncode()
        
        files = []
        for dir_path, _, file_names in os.walk(tmpdir_path):
            for file_name in file_names:
                if file_name.endswith('.tsv'):
                    parent_dir = Path(dir_path)
                    tmp_file_location = parent_dir / file_name
                    
                    new_file_name = f'{parent_dir.name.removesuffix("_tables")}.tsv'
                    new_file_location = destination_dir_path / new_file_name

                    shutil.move(tmp_file_location, new_file_location)

                    files.append(new_file_location)
    
    return files



def normalized_table_name(value):
    new_value = value.removeprefix('db').removeprefix('/').removesuffix('data__').removesuffix('/').removesuffix('_tables')
    if not new_value:
        raise argparse.ArgumentTypeError(f'Failed to normalize table name: "{value}" -> "{new_value}"')
    return new_value

def check_existence_and_return_path_obj(value: str) -> Path:
    path = Path(value).resolve()
    if not path.exists():
        raise argparse.ArgumentTypeError(f'not found - "{value}"')
    return path     


def _init_cli() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser()       

    cli.add_argument(
        '-t', '--table',
        action='append',
        required=True,
        metavar='<table_name>',
        type=normalized_table_name,
        help='table to extract (can be added multiple times)',
    )

    cli.add_argument(
        '-r', '--rpfm',
        required=True,
        metavar='<path>',
        type=check_existence_and_return_path_obj,
        help='path to RPFM installation dir',
    )

    cli.add_argument(
        '-d', '--dest',
        required=True,
        metavar='<path>',
        type=check_existence_and_return_path_obj,
        help='destination directory where store results',
    )

    return cli


def execute(rpfm_path: Path, table_names: list[str], dest: Path) -> list[Path]:
    rpfm = _get_rpfm_dependency_paths(rpfm_path=rpfm_path)
    return _extract_tables(rpfm=rpfm, table_names=table_names, destination_dir_path=dest)


if __name__ == '__main__':
    args = _init_cli().parse_args()
    
    print('Tables to extract (normalized):')
    pprint(args.table)

    execute(
        rpfm_path=args.rpfm,
        table_names=args.table,
        dest=args.dest,
    )
    
    print('Extracted')
