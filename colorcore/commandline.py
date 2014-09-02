# -*- coding: utf-8; -*-
#
# The MIT License (MIT)
#
# Copyright (c) 2014 Flavien Charlon
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import argparse
import bitcoin.base58
import bitcoin.core
import bitcoin.rpc
import inspect
import itertools
import openassets.protocol
import prettytable

def controller(configuration):
    parser = _Router("Colorcore: The colored coins Open Asset client")

    # Commands

    @parser.add
    def getbalance(
            address: "Obtain the balance of this address only"=None,
            minconf: "The minimum number of confirmations (inclusive)"="1",
            maxconf: "The maximum number of confirmations (inclusive)"="9999999"):
        """Obtains the balance of the wallet or an address"""
        client = create_client()
        result = client.listunspent(as_int(minconf), as_int(maxconf), [address] if address else None)

        coloring_engine = create_coloring_engine(client)

        colored_outputs = [coloring_engine.get_output(item["outpoint"].hash, item["outpoint"].n) for item in result]

        table = prettytable.PrettyTable(["Address", "Asset", "Quantity"])

        for script, group in itertools.groupby(colored_outputs, lambda output: output.scriptPubKey):
            total_value = sum([item.nValue for item in group]) / bitcoin.core.COIN
            base58 = get_p2a_address_from_script(script)
            table.add_row([base58, "Bitcoin", str(total_value)])

            for asset_address, outputs in itertools.groupby(group, lambda output: output.asset_address):
                if asset_address is not None:
                    pass

        print(table)

    # Helpers

    def create_client():
        return bitcoin.rpc.Proxy(configuration.rpc_url)

    def create_coloring_engine(client):
        return openassets.protocol.ColoringEngine(client.getrawtransaction, openassets.protocol.OutputCache())

    def as_int(value):
        try:
            return int(value)
        except ValueError:
            raise CommandLineError("Value '{}' is not a valid integer.".format(value))

    def get_p2a_address_from_script(script):
        script_object = bitcoin.core.CScript(script)
        try:
            opcodes = list(script_object.raw_iter())
        except bitcoin.core.script.CScriptInvalidError:
            return "Invalid script"

        if len(opcodes) == 5 and opcodes[0][0] == 0x76 and opcodes[1][0] == 0xA9 \
            and opcodes[3][0] == 0x88 and opcodes[4][0] == 0xac:
            opcode, data, sop_idx = opcodes[2]
            return str(bitcoin.base58.CBase58Data.from_bytes(data, configuration.version_byte))

        return "Unknown script"


    parser.parse()
    return parser


class _Router:
    """Infrastructure for routing command line calls to the right function."""

    def __init__(self, description=None):
        self._parser = argparse.ArgumentParser(description=description)
        self._subparsers = self._parser.add_subparsers()

    def add(self, func):
        subparser = self._subparsers.add_parser(func.__name__, help=func.__doc__)
        subparser.set_defaults(_func=self.filter_errors(func))
        func_signature = inspect.signature(func)
        for name, arg in func_signature.parameters.items():
            if arg.kind != arg.POSITIONAL_OR_KEYWORD:
                continue
            arg_help = arg.annotation if arg.annotation is not arg.empty else None
            if arg.default is arg.empty:
                # a positional argument
                subparser.add_argument(name, help=arg_help)
            else:
                # an optional argument
                subparser.add_argument("--" + name,
                    help=arg_help,
                    nargs="?",
                    default=arg.default)
        return func

    def parse(self):
        args = vars(self._parser.parse_args())
        func = args.pop("_func", self._parser.print_usage)
        func(**args)

    @staticmethod
    def filter_errors(function):
        def decorator(*args, **kwargs):
            try:
                return function(*args, **kwargs)
            except CommandLineError as error:
                print("Error: {}".format(str(error)))

        return decorator


class CommandLineError(Exception):
    pass