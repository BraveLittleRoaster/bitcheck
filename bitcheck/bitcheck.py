import json
import argparse
import blockcypher
from multiprocessing import cpu_count
from multiprocessing.dummy import Pool
from colorama import Fore
from tenacity import retry, retry_if_exception_type, wait_random


class RetryException(Exception):

    def __init__(self):
        # Just raise this for retrying on specific errors.
        pass


class BTCFuncs(object):

    def __init__(self, **kwargs):

        self._v = kwargs.get('verbose')
        self._threads = kwargs.get('threads')
        self._pretty = kwargs.get('pretty')
        self._outfile = kwargs.get('outfile')

    def get_btc_wallet_balance(self, wallet_addr):

        if self._v:
            print(f"{Fore.LIGHTBLACK_EX}[-] Checking balance for {wallet_addr}...")

        satoshis = blockcypher.get_total_balance(wallet_addr.rstrip('\n'), coin_symbol='btc')
        balance = blockcypher.from_satoshis(satoshis)

        if self._v:
            print(f"{Fore.LIGHTGREEN_EX}")

        return {'wallet': wallet_addr, 'balance': balance}

    def multi_wallet_lookup(self, file):

        with open(file, 'r') as f:

            wallets = f.readlines()

        p = Pool()
        for _ in p.imap_unordered(self.get_btc_wallet_balance, wallets):
            print(_)

    def output_to_file(self, wallets):

        pass


def main():

    parser = argparse.ArgumentParser("Bitcheck: check BTC wallet addresses for balances.")

    parser.add_argument('-v', '--verbose', action='store_true', default=False, help='Enable verbose output.')
    parser.add_argument('-w', '--wallet', action='store', help='Check a single wallet address.')
    parser.add_argument('-l', '--list', action='store', help='Input list of wallet addresses (\\n delimited).')
    parser.add_argument('-t', '--threads', action='store', default=cpu_count(), help='Number of threads to use. Default: number of cpus.')

if __name__ == "__main__":

    banner = ""
    print(banner)
    main()
