import os
import re
from functools import reduce
from setdict import SetDict

const_re = re.compile("#\[rustc_args_required_const\(\s*([0-9]+)\s*\)\]")

find_re  = re.compile(
    ""
    + r"((?:(?:#\[[^]]*?\]\s*(?://.*)?\n+)|(?:[\t ]*//[^!].*?\s*\n+))+)" # toplevel declarations or comments
    # + "(#\[rustc_args_required_const\([0-9]+\)\])?\s*" # consts
    # + "((?:(?:#\[[\s\S]*?\]\s*)|(?://.*?\n\s*)))*" # more declarations or comments
    + r"(pub (?:unsafe)? fn (?:[a-zA-z0-9_]*)\s*" # decl + name
    + r"\s*\((?:[^)]*?)\)\s*" # args
    + r"\s*->\s*(?:[a-zA-z0-9_]*)\s*{)", # return type
    flags=re.MULTILINE)

fn_re = re.compile(
    ""
    + r"pub (?:unsafe)? fn ([a-zA-z0-9_]*)\s*" # decl + name
    + r"\s*\(([^)]*?)\)\s*" # args
    + r"\s*->\s*([a-zA-z0-9_]*)\s*{", # return type
    flags=re.MULTILINE)

type_re = re.compile("(?:[sp][sd]|e?[sp][iu][0-9]{1,2})")
int_re = re.compile("e?[sp][iu][0-9]{1,2}")
cvt_re = re.compile("_mm(?:256)?_cvt(e?p[sdiu][0-9]{1,2})_(e?p[sdiu][0-9]{1,2})")
pack_re = re.compile("_mm(?:256)?_packu?s_(e?p[sdiu][0-9]{1,2})")
abs_re = re.compile("_mm(?:256)?_abs_(e?p[sdiu][0-9]{1,2})")

int_maps = {
    "epi64": SetDict({"__m128i": "i64x2", "__m256i": "i64x4"}),
    "epu64": SetDict({"__m128i": "u64x2", "__m256i": "u64x4"}),
    "epi32": SetDict({"__m128i": "i32x4", "__m256i": "i32x8"}),
    "epu32": SetDict({"__m128i": "u32x4", "__m256i": "u32x8"}),
    "epi16": SetDict({"__m128i": "i16x8", "__m256i": "i16x16"}),
    "epu16": SetDict({"__m128i": "u16x8", "__m256i": "u16x16"}),
    "epi8": SetDict({"__m128i": "i8x16", "__m256i": "i8x32"}),
    "epu8": SetDict({"__m128i": "u8x16", "__m256i": "u8x32"})
}

double_map = SetDict({
    "__m128d": "f64x2",
    "__m256d": "f64x4"
})

float_map = SetDict({ # Intel could've made it easy on us...
    "__m256": "f32x8",
    "__m128": "f32x4"
})

def replace_pack(fn, args, ret):
    ret_maps = {
        "epi64": SetDict({"__m128i": "u32x4", "__m256i": "i32x8"}),
        "epu64": SetDict({"__m128i": "u32x4", "__m256i": "u32x8"}),
        "epi32": SetDict({"__m128i": "u16x8", "__m256i": "i16x16"}),
        "epu32": SetDict({"__m128i": "u16x8", "__m256i": "u16x16"}),
        "epi16": SetDict({"__m128i": "u8x16", "__m256i": "i8x32"}),
        "epu16": SetDict({"__m128i": "u8x16", "__m256i": "u8x32"})
    }

    suffix = next(type_re.finditer(fn)).group()
    arg_map = int_maps.get(suffix, SetDict())
    ret_map = ret_maps.get(suffix, SetDict())

    sub_many = lambda string: lambda acc, it: re.sub(f"{it[0]}$", it[1], acc or string)
    master_map = arg_map | double_map | float_map

    return ([[arg[0], reduce(sub_many(arg[1]), master_map.items(), "")] for arg in args],
            reduce(sub_many(ret), (ret_map | double_map | float_map).items(), ""))

def replace_abs(fn, args, ret):
    ret_maps = {
        "epi64": SetDict({"__m128i": "u64x2", "__m256i": "u64x4"}),
        "epu64": SetDict({"__m128i": "u64x2", "__m256i": "u64x4"}),
        "epi32": SetDict({"__m128i": "u32x4", "__m256i": "u32x8"}),
        "epu32": SetDict({"__m128i": "u32x4", "__m256i": "u32x8"}),
        "epi16": SetDict({"__m128i": "u16x8", "__m256i": "u16x16"}),
        "epu16": SetDict({"__m128i": "u16x8", "__m256i": "u16x16"}),
        "epi8": SetDict({"__m128i": "u8x16", "__m256i": "u8x32"}),
        "epu8": SetDict({"__m128i": "u8x16", "__m256i": "u8x32"})
    }

    suffix = next(type_re.finditer(fn)).group()
    int_map = int_maps.get(suffix, SetDict())
    ret_map = ret_maps.get(suffix, SetDict())

    sub_many = lambda string: lambda acc, it: re.sub(f"{it[0]}$", it[1], acc or string)
    master_map = int_map | double_map | float_map
    return ([[arg[0], reduce(sub_many(arg[1]), master_map.items(), "")] for arg in args],
            reduce(sub_many(ret), (ret_map | double_map | float_map).items(), ""))

def replace_cvt(fn, args, ret):
    from_, to = next(cvt_re.finditer(fn)).groups()

    arg_map = int_maps.get(from_, SetDict())
    ret_map = int_maps.get(to, SetDict())

    sub_many = lambda string: lambda acc, it: re.sub(f"{it[0]}$", it[1], acc or string)
    master_map = arg_map | double_map | float_map

    return ([[arg[0], reduce(sub_many(arg[1]), master_map.items(), "")] for arg in args],
            reduce(sub_many(ret), (ret_map | double_map | float_map).items(), ""))

def replace_default(fn, args, ret):
    int_map = int_maps.get(next(int_re.finditer(fn)).group(), SetDict()) if int_re.search(fn) else {}
    sub_many = lambda string: lambda acc, it: re.sub(f"{it[0]}$", it[1], acc or string)
    master_map = int_map | double_map | float_map

    return ([[arg[0], reduce(sub_many(arg[1]), master_map.items(), "")] for arg in args],
            reduce(sub_many(ret), master_map.items(), ""))

def body_string(decls, fn, args):
    constindices = ({int(m.groups()[0]) for m in re.finditer(const_re, decls)}
                    if "rustc_args_required_const" in decls
                    else set())

    if constindices:
        constified = (name if i not in constindices else "$imm8"
                      for i, (name, _) in enumerate(args))

        formatted = ", ".join(f"crate::mem::transmute({name})" if name != "$imm8" else name
                              for name in constified)

        # TODO: >1 const argument
        const_arg = args[list(constindices)[0]][0]

        # Call site to be passed to constify_imm8
        return f"""
    macro_rules! call {{
        ($imm8:expr) => {{
            crate::myarch::{fn}({formatted})
        }};
    }}

    crate::mem::transmute(constify_imm8!({const_arg}, call))\n"""
    else:
        return f"    crate::mem::transmute(crate::myarch::{fn}({', '.join(f'crate::mem::transmute({argname})' if argname != 'imm8' else argname for argname, _ in args)}))\n"

def transformations(fn):
    all_transformations = {
        cvt_re: replace_cvt,
        pack_re: replace_pack,
        abs_re: replace_abs
    }

    for re_, transformation in all_transformations.items():
        if re_.match(fn):
            return transformation

    return replace_default

def transform_file(infile, outfile):
    outfile.write(f"#![allow(unused_imports)]\n")
    outfile.write(f"use crate::myarch::*;\n")
    outfile.write(f"use crate::simd::*;\n\n")

    file_str = infile.read()

    for decls, fnline in map(lambda m: m.groups(), re.finditer(find_re, file_str)):
        fn, args, ret = next(map(lambda m: m.groups(), re.finditer(fn_re, fnline)))

        args = [[s.strip() for s in name_type.split(":") if s.strip() != ""]
                for name_type in args.split(",")
                if args != "" and name_type != ""
                if [s.strip() for s in name_type.split(":") if s.strip() != ""]]

        args, ret = transformations(fn)(fn, args, ret)

        # Write the header
        outfile.write(decls)
        outfile.write(f"pub unsafe fn {fn}(")

        for name, type_ in args[:-1]:
            outfile.write(f"{name}: {type_}, ")

        if args != []:
            outfile.write(f"{args[-1][0]}: {args[-1][1]}")

        outfile.write(f") -> {ret} {{\n")

        # Write the body
        outfile.write(body_string(decls, fn, args))
        outfile.write(f"}}\n\n")

if True or __name__ == "__main__":
    for arch in ["x86", "x86_64"]:
        cwd = os.getcwd()

        if not os.path.exists(cwd + f"/vektor/src/{arch}"):
            os.makedirs(cwd + f"/vektor/src/{arch}")

        files_to_scan = (f for f in os.scandir(cwd + f"/stdsimd/coresimd/{arch}")
                         if f.name not in ["mod.rs"])

        for entry in files_to_scan:
            with open(entry.path) as infile:
                with open(cwd + f"/vektor/src/{arch}/{entry.name}", "w") as outfile:
                    transform_file(infile, outfile)
