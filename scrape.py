import os
import re

fn_re = re.compile(
    "#\\[target_feature\\(enable\s*=\s*\"([A-Za-z0-9_,.]*)\"\\)\\]\s*" # feature
    + "(?:(?:#\\[[\s\S]*?\\]\s*)|(?://.*?\n\s*))*" # more declarations or comments
    #\s*(?:(?://.*)|(?:#\\[.*\\])\n)*"
    + "pub (?:unsafe)? fn ([a-zA-z0-9_]*)\s*" # decl + name
    + "\s*\\(([^)]*?)\\)\s*" # args
    + "\s*->\s*([a-zA-z0-9_]*)\s*{", # return type
    flags=re.MULTILINE)

for arch in ["x86", "x86_64"]:
    if not os.path.exists(os.getcwd() + f"/vektor/src/{arch}"):
        os.makedirs(os.getcwd() + f"/vektor/src/{arch}")
    for entry in os.scandir(os.getcwd() + f"/stdsimd/coresimd/{arch}"):
        if entry.name == "mod.rs":
            continue
        with open(os.getcwd() + f"/vektor/src/{arch}/{entry.name}", "w") as outfile:
            with open(entry.path) as infile:

                outfile.write(f"use ::arch::{arch}::*;\n")
                outfile.write(f"use ::simd::*;\n\n")

                file_str = infile.read()

                for feature, name, args, ret in map(lambda m: m.groups(), re.finditer(fn_re, file_str)):
                    int_map = [("epi64", "i64x2", "i64x4"),
                               ("epu64", "u64x2", "u64x4"),
                               ("epi32", "i32x4", "i32x8"),
                               ("epu32", "u32x4", "u32x8"),
                               ("epi16", "i16x8", "i16x16"),
                               ("epu16", "u16x8", "u16x16"),
                               ("epi8", "u8x16", "i8x32"),
                               ("epu8", "u8x16", "u8x32")]

                    double_map = {
                        "__m128d": "f64x2",
                        "__m256d": "f64x4"
                    }

                    float_map = { # Intel could've made it easy on us...
                        "__m256": "f32x8",
                        "__m128": "f32x4"
                    }

                    for suffix, sse, avx in int_map:
                        if name.endswith(suffix):
                            ret = ret.replace("__m128i", sse)
                            ret = ret.replace("__m256i", avx)

                    for k, v in double_map.items():
                        ret = ret.replace(k, v)

                    for k, v in float_map.items():
                        ret = (ret
                               .replace("__m128d", "__VEKTOR_GEN_M128D")
                               .replace("__m128i", "__VEKTOR_GEN_M128I")
                               .replace("__m256d", "__VEKTOR_GEN_M256D")
                               .replace("__m256i", "__VEKTOR_GEN_M256I")
                               .replace(k, v)
                               .replace("__VEKTOR_GEN_M128D", "__m128d")
                               .replace("__VEKTOR_GEN_M128I", "__m128i")
                               .replace("__VEKTOR_GEN_M256D", "__m256d")
                               .replace("__VEKTOR_GEN_M256I", "__m256i"))

                    processed_args = []
                    splitargs = filter(lambda a: a.strip() != "", args.split(",") if args != "" else [])
                    for argname, argtype in map(lambda a: a.split(":"), splitargs):
                        argname = argname.strip()
                        argtype = argtype.strip()
                        for suffix, sse, avx in int_map:
                            if name.endswith(suffix) and "gather" not in name:
                                if argname in ["a", "b", "c", "d", "mask", "x", "y", "z"]:
                                    argtype = argtype.replace("__m128i", sse)
                                    argtype = argtype.replace("__m256i", avx)
                                    ret = ret.replace("__m128i", sse)
                                    ret = ret.replace("__m256i", avx)

                        for k, v in double_map.items():
                            ret = ret.replace(k, v)

                        for k, v in float_map.items():
                            argtype = (argtype
                                       .replace("__m128d", "__VEKTOR_GEN_M128D")
                                       .replace("__m128i", "__VEKTOR_GEN_M128I")
                                       .replace("__m256d", "__VEKTOR_GEN_M256D")
                                       .replace("__m256i", "__VEKTOR_GEN_M256I")
                                       .replace(k, v)
                                       .replace("__VEKTOR_GEN_M128D", "__m128d")
                                       .replace("__VEKTOR_GEN_M128I", "__m128i")
                                       .replace("__VEKTOR_GEN_M256D", "__m256d")
                                       .replace("__VEKTOR_GEN_M256I", "__m256i"))

                        processed_args.append((argname, argtype))

                    outfile.write(f"#[inline]\n")
                    outfile.write(f"#[target_feature(enable = \"{feature}\")]\n")
                    outfile.write(f"pub unsafe fn {name}(")

                    for argname, argtype in processed_args[:-1]:
                        outfile.write(f"{argname}: {argtype}, ")

                    if processed_args != []:
                        outfile.write(f"{processed_args[-1][0]}: {processed_args[-1][1]}")

                    outfile.write(f") -> {ret} {{\n")
                    outfile.write(f"    ::mem::transmute(::arch::{arch}::{name}({', '.join(f'::mem::transmute({argname})' for argname, _ in processed_args)}))\n")
                    outfile.write(f"}}\n\n")
