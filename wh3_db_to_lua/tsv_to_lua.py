import argparse
import glob
import re 
from functools import partial
from pathlib import Path
from pprint import pprint
from typing import Optional



_is_not_string = re.compile(r'^true$|^false$|^-?[\d]+(\.[\d]+)?$')



def _should_not_wrap_as_string(value: str) -> bool:
    return bool(_is_not_string.match(value))


def _build_lua_indexed_table(tsv_line: str) -> str:
    fields = [
        f'[{i}] = {field if _should_not_wrap_as_string(field) else f"[=[{field}]=]"}' 
        for i, field in enumerate(tsv_line.split('\t'), start=1)
    ]

    return f'{{ {", ".join(fields)} }}'


def _build_lua_kv_table(tsv_line: str, columns: list[str]) -> str:
    fields = [
        f'["{column}"] = {field if _should_not_wrap_as_string(field) else f"[=[{field}]=]"}' 
        for column, field in zip(columns, tsv_line.split('\t'))
    ]

    return f'{{ {", ".join(fields)} }}'


def tsv_to_lua_table(tsv_file_path: Path, map_columns: bool) -> str:
    with tsv_file_path.open() as tsv:
        columns_line = tsv.readline().strip()
        assert columns_line, f'no columns found (empty file?): "{tsv_file_path}"'

        line = tsv.readline()
        assert line and line.startswith('#'), f'invalid file format (not RPFM .tsv?): "{tsv_file_path}"'

        columns = columns_line.split('\t')

        if map_columns:
            build_lua_record = partial(_build_lua_kv_table, columns=columns)
        else:
            build_lua_record = _build_lua_indexed_table

        records = []
        line = tsv.readline().strip()
        while line:
            records.append(build_lua_record(line))
            line = tsv.readline().strip()

        if not records:
            return ''
        

        dumped_lua_table_rows = ',\n  '.join(
            f'[{i}] = {record}'
            for i, record in enumerate(records, start=1)
        )
        
        dumped_lua_table = f'{{\n  {dumped_lua_table_rows}\n}}'
        
    return dumped_lua_table


def _get_tsv_files_in_directory(directory: Path | str) -> list[Path]:
    if not isinstance(directory, Path):
        directory = Path(directory)
        assert directory.exists()
    
    assert isinstance(directory, Path), f'invalid type of directory argument: {type(directory)}'

    return [directory / Path(file) for file in glob.glob('*.tsv', root_dir=str(directory))]


def _convert_all_files(files: list[Path], *, map_columns: bool, add_return: bool, dest: Optional[Path]) -> None:
    for file in files:
        lua_table = tsv_to_lua_table(file, map_columns=map_columns)
        if add_return:
            lua_table = f'return {lua_table}'
        
        directory = file.parent if dest is None else dest

        (directory / f'{file.name.removesuffix(".tsv")}.lua').write_text(lua_table)


def _remove_source_files(files: list[Path]) -> None:
    for file in files:
        file.unlink(missing_ok=True)


def _init_cli() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser()

    def check_existence_and_return_path_obj(value: str) -> Path:
        path = Path(value).resolve()
        if not path.exists():
            raise argparse.ArgumentTypeError(f'not found - "{value}"')
        return path

    def check_file_extension_and_existence(value: str) -> Path:
        if not value.endswith('.tsv'):
            raise argparse.ArgumentTypeError(f'file does not have .tsv extension - "{value}"')
        
        return check_existence_and_return_path_obj(value)

    sources = cli.add_mutually_exclusive_group(required=True)
    sources.add_argument(
        '-f', '--file',
        action='append',
        metavar='<path>',
        type=check_file_extension_and_existence,
        help='path to .tsv file from RPFM to convert (can be added multiple times)',
    )

    sources.add_argument(
        '-d', '--directory',
        metavar='<path>',
        type=check_existence_and_return_path_obj,
        help='set directory in which to convert all .tsv to .lua',
    )

    destination = cli.add_mutually_exclusive_group()

    destination.add_argument(
        '--dest',
        metavar='<path>',
        type=check_existence_and_return_path_obj,
        help='set different output location (default: same directory)',
    )

    destination.add_argument(
        '--replace',
        action='store_true',
        help='replace original files with converted versions',
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

    return cli


def execute(files: list[Path], dest: Optional[Path], should_replace: bool, map_columns: bool, add_return: bool) -> None:
    _convert_all_files(files, map_columns=map_columns, add_return=add_return, dest=dest)

    if should_replace:
        _remove_source_files(files)


if __name__ == '__main__':
    args = _init_cli().parse_args()

    files = args.file if args.file else _get_tsv_files_in_directory(args.directory)

    print('Files to convert:')
    pprint([file.name for file in files])

    execute(
        files,
        args.dest,
        should_replace=args.replace,
        map_columns=args.map_columns,
        add_return=args.add_return,
    )

    print('Converted')        
