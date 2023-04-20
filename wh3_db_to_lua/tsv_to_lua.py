import argparse
import glob
import os
import re 
from hashlib import md5
from pathlib import Path
from pprint import pprint
from typing import Callable, NamedTuple, Iterable, TextIO, TypeAlias


LuaKeyBuilder:   TypeAlias = Callable[[int, str], str]
LuaValueBuilder: TypeAlias = Callable[[str, int, str], str]
LuaRowBuilder:   TypeAlias = Callable[[str], str]
LuaTableDump:    TypeAlias = Callable[[str], str]

ValueConverter:  TypeAlias = Callable[[str], str]
FieldConverters: TypeAlias = dict[str, ValueConverter]


RPFM_META_PATT = re.compile(r'^#(?P<table>[\w]+);(?P<version>[\d]+);')
MAX_ERR_LEN: int = 1000


class RecordNDigest(NamedTuple):
    record: str
    digest: str


# ========================================================================================================================================
#                                                      Main
# ========================================================================================================================================


def execute(files: list[Path], dest: Path | None, should_replace: bool, map_columns: bool, add_return: bool, calculate_md5: bool) -> None:
    _convert_all_files(
        files,
        schema=_get_rpfm_db_schema(),
        map_columns=map_columns,
        add_return=add_return,
        dest=dest,
        md5=calculate_md5,
    )

    if should_replace:
        _remove_source_files(files)


def tsv_to_lua_table(tsv_file_path: Path, schema: dict|None, *, map_columns: bool, md5: bool) -> str:
    with tsv_file_path.open() as tsv:
        get_next_line = _file_iterator(tsv)

        columns_line = get_next_line()
        assert columns_line, f'no columns found (empty file?): "{tsv_file_path}"'

        rpfm_meta = RPFM_META_PATT.match(get_next_line())
        assert rpfm_meta, f'invalid file format (not RPFM .tsv?): "{tsv_file_path}"'


        build_lua_record, dump_lua_table = _get_data_builders(
            schema=schema,
            columns=columns_line.split('\t'),
            table_name=rpfm_meta.group('table'),
            version=int(rpfm_meta.group('version')),
            map_columns=map_columns,
            md5=md5,
        )


        records = []
        while line := get_next_line():
            records.append(build_lua_record(line))

        if not records:
            return ''

    return dump_lua_table(records)


# ========================================================================================================================================
#                                                      auxillary stuff
# ========================================================================================================================================


def _file_iterator(tsv: TextIO) -> Callable[[], str]:
    def _generator():
        while line := tsv.readline():
            yield line.strip()
    
    def _factory(gen):
        def _get_next_value():
            return next(gen, None)
        return _get_next_value
    
    return _factory(_generator())


def _get_tsv_files_in_directory(directory: Path | str) -> list[Path]:
    if not isinstance(directory, Path):
        directory = Path(directory)
        assert directory.exists()
    
    assert isinstance(directory, Path), f'invalid type of directory argument: {type(directory)}'

    return [directory / Path(file) for file in glob.glob('*.tsv', root_dir=str(directory))]


def _convert_all_files(files: list[Path], *, schema=dict|None, map_columns: bool, add_return: bool, dest: Path | None, md5: bool) -> None:
    for file in files:
        lua_table = tsv_to_lua_table(file, schema, map_columns=map_columns, md5=md5)
        if add_return:
            lua_table = f'return {lua_table}'
        
        directory = file.parent if dest is None else dest

        (directory / f'{file.name.removesuffix(".tsv")}.lua').write_text(lua_table)


def _remove_source_files(files: list[Path]) -> None:
    for file in files:
        file.unlink(missing_ok=True)


def _get_hex_digest(s: str) -> str:
    return md5(s.encode(), usedforsecurity=False).hexdigest()


# ========================================================================================================================================
#                                                   Common stuff
# ========================================================================================================================================


def _get_data_builders(schema: dict|None, columns: list[str], table_name: str, version: int, map_columns: bool, md5: bool) -> tuple[LuaRowBuilder, LuaTableDump]:
    key_builder    = _key_builder_factory(map_columns)
    value_builder  = _build_value_from_rust_types__factory(schema, table_name, version)
    if not value_builder:
        print("Fallback to manual type determination (may be inaccurate)")
        value_builder = _build_value_legacy

    record_builder = _record_dumper_factory(key_builder, value_builder, columns=columns, calculate_md5=md5)
    table_dumper   = _table_dumper_factory(calculate_md5=md5)

    return record_builder, table_dumper



def _key_builder_factory(map_columns: bool) -> LuaKeyBuilder:
    def _build_indexed_key(pos: int, column: str) -> str:
        return f'[{pos}]'
    
    def _build_normal_key(pos: int, column: str) -> str:
        return f'["{column}"]'
    
    return _build_normal_key if map_columns else _build_indexed_key


def _table_dumper_factory(calculate_md5: bool) -> LuaTableDump:
    def _dump_records(records: list[RecordNDigest], delim: str) -> str:
        return delim.join(
            f'[{i}] = {record}'
            for i, (record, _) in enumerate(records, start=1)
        )

    def _form_default_lua_table(records: list[RecordNDigest]) -> str:
        dumped_records = _dump_records(records, delim=',\n  ')
        return f'{{\n  {dumped_records}\n}}'

    def _form_lua_table_with_md5(records: list[tuple[str, int]]) -> str:
        dumped_records = _dump_records(records, delim=',\n    ')
        stable_agg_checksum = _get_hex_digest(''.join(sorted(digest for _, digest in records)))

        return f'{{\n  ["checksum"]="{stable_agg_checksum}",\n  ["records"]={{\n    {dumped_records}\n  }}\n}}'


    return _form_lua_table_with_md5 if calculate_md5 else _form_default_lua_table



def _record_dumper_factory(build_key: LuaKeyBuilder, build_value: LuaValueBuilder, *, columns: list[str], calculate_md5: bool) -> Callable[[str], RecordNDigest]:
    def _dump_as_lua_table(fields: list[str]) -> str:
        lua_table_kv = [
            '{k}={v}'.format(
                k=build_key(i, column),
                v=build_value(field, i, column),
            )
            for i, (column, field) in enumerate(zip(columns, fields), start=1)
        ]

        return '{%s}' % (','.join(lua_table_kv))

    

    def dump_record(tsv_line: str) -> RecordNDigest:
        dumped_lua_table = _dump_as_lua_table(tsv_line.split('\t'))
        return RecordNDigest(dumped_lua_table, None)


    def to_str(field) -> str:
        return str(to_lua_num(field) if is_float(field) else field)

    def dump_record_and_calc_md5(tsv_line: str) -> RecordNDigest:
        fields = tsv_line.split('\t')
        dumped_lua_table = _dump_as_lua_table(fields)

        sorted_fields = ''.join(sorted(to_str(f) for f in fields))
        digest = _get_hex_digest(sorted_fields)

        return RecordNDigest(dumped_lua_table, digest)
    

    return dump_record_and_calc_md5 if calculate_md5 else dump_record



# ========================================================================================================================================
#                                       LEGACY dump tsv field using some assumptions (May be inaccurate)
# ========================================================================================================================================


def _match_type(pattern) -> Callable[[str], re.Match|None]:
    pat = re.compile(pattern)
    def check(v): return pat.match(v)
    return check


is_int     = _match_type(r'^-?[\d]+?$')
is_float   = _match_type(r'^(?P<int>-?[\d]+)\.(?P<fraction>[\d]+)$')
is_float   = _match_type(r'^(?P<int>-?[\d]+)\.(?P<fraction>[\d]+)$')

is_boolean = _match_type(r'^true$|^false$')

str_val = '[=[{v}]=]'


def _get_shortest_number_repr(match: re.Match) -> str:
    if int(match.group('fraction')) == 0:
        return match.group('int')
    return str(float(match.string))


def _build_value_legacy(value: str, pos: int, column: str) -> str:
    if pos == 1: 
        return str_val.format(v=value)
    
    if is_boolean(value):
        return value
    
    if is_int(value):
        return value

    if match := is_float(value):
        return _get_shortest_number_repr(match)
    
    return str_val.format(v=value)



# ========================================================================================================================================
#                                       Dump tsv field using db .ron schema
# ========================================================================================================================================



_ret_same_val: ValueConverter = lambda v: v

to_lua_bool:   ValueConverter = _ret_same_val
to_lua_str:    ValueConverter = lambda v: f'[=[{v}]=]'
to_lua_num:    ValueConverter = lambda v: str(_get_shortest_repr_without_trailing_zeros(v))


RUST_TYPE_TO_LUA: dict[str, ValueConverter] = {
    'Boolean':          to_lua_bool,
    'ColourRGB':        to_lua_str,   # something like: FFFFFF
    'F32':              to_lua_num,
    'F64':              to_lua_str,
    'I32':              to_lua_num,
    'I64':              to_lua_str,
    'OptionalStringU8': to_lua_str,
    'StringU8':         to_lua_str,
    'StringU16':        to_lua_str,
}



def _get_shortest_repr_without_trailing_zeros(v):
    f = float(v); i = int(f)
    return i if i == f else f


def _get_rpfm_db_schema() -> dict | None:
    schemas_path = Path(os.getenv('APPDATA')) / 'rpfm/config/schemas/schema_wh3.ron'
    if not schemas_path.exists():
        print(f'Failed to get WH3 schema at path: "{schemas_path}"')
        return
    
    with schemas_path.open(encoding='utf-8') as file:
        prepared_schema_content = file.read().replace(r"\'", r'\"').replace(r'\u', r'\n')
    
    try:
        import pyron
        schema = pyron.loads(prepared_schema_content, preserve_class_names=True, print_errors=False)
    except Exception as err:
        if len(err := str(err)) > MAX_ERR_LEN: err = (f'{{:.{MAX_ERR_LEN}}}...<truncated>').format(err)
        print(f'Failed to load RON (RustObjectNotation) file:\n{err}')
        return
    
    return schema


def _build_value_from_rust_types__factory(schema: dict|None, table_name: str, version: int) -> LuaValueBuilder|None:
    if not schema:
        return print("No schema provided")
    
    converters = _get_field_conterters(schema, table_name=table_name, version=version)
    if not converters:
        return print("Failed to build converters")
    
    def _dump_value(value: str, pos: int, column: str) -> str:
        converter = converters.get(column)
        assert converter, f"wtf!?: converters.get('{column}') = None"
        return converter(value)

    return _dump_value


def _get_rust_type(field_definition: dict) -> str:
    return field_definition.get('field_type', {}).get('!__name__')



def _get_field_conterters(schema: dict, table_name: str, version: int) -> FieldConverters | None:
    table_definition = None
    definitions = schema.get('definitions', {}).get(table_name, [])
    unknown = -99999

    for def_vN in definitions:
        if int(def_vN.get('version', unknown)) != version:
            continue

        if isinstance(def_vN.get('fields'), Iterable):
            table_definition = def_vN
            break

        print(f'Invalid schema provided: missing "fields" key, or it is an invalid type: {type(def_vN.get("fields"))}')
        return

    if not table_definition:
        print(f'Neither one occured: 1) invalid schema provided; 2) table "{table_name}" not found; 3) missing desired table version "{version}"')
        return 

    column_converters = {}
    for field_def in table_definition['fields']:
        converter = RUST_TYPE_TO_LUA.get(_get_rust_type(field_def))
        field_name = field_def.get('name')
        if not all((converter, field_name)):
            print(f'Failed to get converter for type "{field_def.get("field_type")}" for field "{field_def["name"]}" ({table_name})')
            return
        
        column_converters[field_name] = converter
    
    if not len(column_converters):
        print('Failed to build table field converters (no columns found)')
        return
    
    return column_converters


# ========================================================================================================================================
#                                                               CLI
# ========================================================================================================================================


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

    cli.add_argument(
        '--md5',
        action='store_true',
        help='calculate md5_checksum. WARNING: this will lead to different output table structure',
    )

    return cli


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
        calculate_md5=args.md5,
    )

    print('Converted')        
