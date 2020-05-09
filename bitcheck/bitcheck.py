import os
import sys
import json
import tqdm
import requests
import argparse
import blockcypher
from fake_useragent import UserAgent
from multiprocessing import cpu_count
from multiprocessing.dummy import Pool
from ssl import SSLError
from bs4 import BeautifulSoup
from colorama import Fore
from tenacity import retry, retry_if_exception_type, wait_random


class RetryException(Exception):

    def __init__(self):
        # Just raise this for retrying on specific errors.
        pass


class BTCFuncs(object):

    def __init__(self, **kwargs):

        self._v = kwargs.get('verbose')
        self._threads = int(kwargs.get('threads'))
        self._outfile = kwargs.get('outfile')
        self._apiKey = kwargs.get('apiKey')
        self._proxy = kwargs.get('proxy')
        self._provider = kwargs.get('provider')

        if self._proxy and self._v:
            print(f"[-] Using proxy: {self._proxy}")

    @retry(retry=retry_if_exception_type(RetryException), wait=wait_random(30, 60))
    def get_btc_wallet_bal_blockcypher(self, wallet_addr):

        wallet = wallet_addr.rstrip('\n')

        if self._v:
            print(f"{Fore.LIGHTBLACK_EX}[-] Checking balance for {wallet}...{Fore.RESET}")
        try:
            satoshis = blockcypher.get_total_balance(wallet, coin_symbol='btc', api_key=self._apiKey)
            balance = blockcypher.from_satoshis(satoshis, output_type='btc')
        except blockcypher.api.RateLimitError:
            if self._v:
                print(f"{Fore.LIGHTBLACK_EX}[~] {wallet}: API Rate limit hit... cooling down thread for 30 to 60 seconds.{Fore.RESET}")
            raise RetryException

        except IndexError:
            if self._v:
                print(f"{Fore.YELLOW}[*] WARN: Invalid wallet address: {repr(wallet)}. Skipping...{Fore.RESET}")
            return {'wallet': None, 'balance': 0.0}

        if balance > 0:
            print(f"{Fore.LIGHTGREEN_EX}[$] Wallet: {wallet}, Balance: {balance}{Fore.RESET}")
        else:
            if self._v:
                print(f"{Fore.LIGHTBLACK_EX}[-] Wallet: {wallet}, Balance: {balance}{Fore.RESET}")

        return {'wallet': wallet, 'balance': balance}

    @retry(retry=retry_if_exception_type(RetryException), wait=wait_random(30, 60))
    def get_btc_wallet_bal_bitref(self, wallet_addr):

        base_url = f"https://bitref.com/"
        wallet = wallet_addr.rstrip('\n')
        url = base_url + wallet

        ua = UserAgent()

        headers = {
            "User-Agent": ua.firefox
        }
        if self._v:
            print(f"{Fore.LIGHTBLACK_EX}[-] Checking balance for {wallet}...{Fore.RESET}")

        if self._proxy:

            proxy_protocol = self._proxy.split(":")[0]
            proxies = {
                proxy_protocol: self._proxy
            }

            try:
                req = requests.get(url, headers=headers, proxies=proxies)
            except (requests.exceptions.ConnectionError, requests.exceptions.ConnectTimeout):
                raise RetryException

        else:
            try:
                req = requests.get(url, headers=headers)
            except (requests.exceptions.ConnectionError, requests.exceptions.ConnectTimeout):
                raise RetryException

        html = req.content.decode('utf-8')
        soup = BeautifulSoup(html, 'html.parser')

        bal_span = soup.find("span", {"id": "final_balance"})
        balance = float(bal_span.text)

        if balance > 0:
            print(f"{Fore.LIGHTGREEN_EX}[$] Wallet: {wallet}, Balance: {balance}{Fore.RESET}")
        else:
            if self._v:
                print(f"{Fore.LIGHTBLACK_EX}[-] Wallet: {wallet}, Balance: {balance}{Fore.RESET}")

        return {'wallet': wallet, 'balance': balance}

    @retry(retry=retry_if_exception_type(RetryException), wait=wait_random(30, 60))
    def get_btc_wallet_bal_blockchaininfo(self, wallet_addr):

        base_url = "https://blockchain.info/rawaddr/"
        wallet = wallet_addr.rstrip('\n')
        url = base_url + wallet

        ua = UserAgent()

        headers = {
            "User-Agent": ua.firefox
        }

        if self._v:
            print(f"{Fore.LIGHTBLACK_EX}[-] Checking balance for {wallet} @ {self._provider}{Fore.RESET}")

        if self._proxy:

            proxy_protocol = self._proxy.split(":")[0]
            proxies = {
                proxy_protocol: self._proxy
            }

            try:
                req = requests.get(url, headers=headers, proxies=proxies, verify=False)
            except (requests.exceptions.ConnectionError, requests.exceptions.ConnectTimeout, ss) as e:
                if self._v:
                    print(f"{Fore.LIGHTBLACK_EX}[~] {self._provider}: ERROR: {e}. Retrying...{Fore.RESET}")

                raise RetryException

        else:
            try:
                req = requests.get(url, headers=headers)
            except (requests.exceptions.ConnectionError, requests.exceptions.ConnectTimeout) as e:
                if self._v:
                    print(f"{Fore.LIGHTBLACK_EX}[~] {self._provider}: ERROR: {e}. Retrying...{Fore.RESET}")
                raise RetryException

        html = req.content.decode('utf-8')

        try:
            json_data = json.loads(html)
        except json.decoder.JSONDecodeError as e:
            if self._v:
                print(f"{Fore.LIGHTBLACK_EX}[~] WARN: {wallet} @ Got a JSON decode error. May be cloudflare. Will retry: {e}{Fore.RESET}")
            raise RetryException

        balance = json_data.get('final_balance')
        balance = blockcypher.from_satoshis(balance, output_type='btc')

        if balance > 0:
            bal = "{0:.10f}".format(balance)
            print(f"{Fore.LIGHTGREEN_EX}[$] {self._provider}: Wallet: {wallet}, Balance: {bal}{Fore.RESET}")
        else:
            if self._v:
                print(f"{Fore.LIGHTBLACK_EX}[-] {self._provider}: Wallet: {wallet}, Balance: {balance}{Fore.RESET}")

        return {'wallet': wallet, 'balance': balance}

    def multi_wallet_lookup(self, file, provider):

        self._provider = provider
        balances = []
        results = []

        with open(file, 'r') as f:

            wallets = f.readlines()

        p = Pool(processes=self._threads)
        if provider == 'blockcypher':
            for _ in tqdm.tqdm(p.imap_unordered(self.get_btc_wallet_bal_blockcypher, wallets), total=len(wallets)):
                if _.get('balance') > 0:
                    balances.append(_.get('balance'))
                results.append(_)
        elif provider == 'blockchain-info':
            for _ in tqdm.tqdm(p.imap_unordered(self.get_btc_wallet_bal_blockchaininfo, wallets), total=len(wallets)):
                if _.get('balance') > 0:
                    balances.append(_.get('balance'))
                results.append(_)
        else:
            for _ in tqdm.tqdm(p.imap_unordered(self.get_btc_wallet_bal_bitref, wallets), total=len(wallets)):
                if _.get('balance') > 0:
                    balances.append(_.get('balance'))
                results.append(_)

        print(f"{Fore.LIGHTBLUE_EX}[+] Found a total of {sum(balances)} from {len(results)} checked wallets.")

        f.close()

        return results

    def output_to_file(self, wallets):

        if self._v:
            print(f"{Fore.LIGHTBLACK_EX}[-] Dumping {len(wallets)} results.{Fore.RESET}")

        with open(self._outfile, 'w') as f:

            for wallet in wallets:
                f.write(f"{json.dumps(wallet)}\n")

        f.close()


def main():

    banner = """ 
     /$$$$$$$  /$$   /$$      /$$$$$$  /$$                           /$$      
    | $$__  $$|__/  | $$     /$$__  $$| $$                          | $$      
    | $$  \\ $$ /$$ /$$$$$$  | $$  \\__/| $$$$$$$   /$$$$$$   /$$$$$$$| $$   /$$
    | $$$$$$$ | $$|_  $$_/  | $$      | $$__  $$ /$$__  $$ /$$_____/| $$  /$$/
    | $$__  $$| $$  | $$    | $$      | $$  \\ $$| $$$$$$$$| $$      | $$$$$$/ 
    | $$  \\ $$| $$  | $$ /$$| $$    $$| $$  | $$| $$_____/| $$      | $$_  $$ 
    | $$$$$$$/| $$  |  $$$$/|  $$$$$$/| $$  | $$|  $$$$$$$|  $$$$$$$| $$ \\  $$
    |_______/ |__/   \\___/   \\______/ |__/  |__/ \\_______/ \\_______/|__/  \\__/

        """
    print(Fore.LIGHTGREEN_EX + banner + Fore.RESET)

    parser = argparse.ArgumentParser("Check BTC wallet addresses for balances.")

    parser.add_argument('-v', '--verbose', action='store_true', default=False, help='Enable verbose output.')
    parser.add_argument('-w', '--wallet', action='store', help='Check a single wallet address.')
    parser.add_argument('-l', '--list', action='store', help='Input list of wallet addresses (\\n delimited).')
    parser.add_argument('-t', '--threads', action='store', default=cpu_count(),
                        help='Number of threads to use. Default: number of cpus.')
    parser.add_argument('-o', '--output', action='store', help='Name of file to output JSON results to.')
    parser.add_argument('-k', '--key', action='store', default=None,
                        help='BlockCypher API Key to use for requests for higher rate limit.')
    parser.add_argument('-p', '--proxy', action='store',
                        help='Use the proxy. Example: socks4://admin:admin@127.0.0.1:9050')

    provider = parser.add_argument_group("Provider Options")
    provider.add_argument('--blockcypher', action='store_true', help='Use BlockCypher for getting balances.')
    provider.add_argument('--bitref', action='store_true', help='(Default) Use bitref.com for getting balances.')
    provider.add_argument('--blockchain-info', action='store_true', help='Use Blockchain.info for getting balances.')

    args = parser.parse_args()

    btc = BTCFuncs(
        verbose=args.verbose,
        threads=args.threads,
        outfile=args.output,
        apiKey=args.key,
        proxy=args.proxy
    )

    if args.wallet and args.list:
        print(f"{Fore.RED}[!] Specify either --wallet OR --list, not both. Exiting.{Fore.RESET}")
        sys.exit(1)

    if args.wallet:
        if args.blockcypher:
            print(f"[-] Checking using blockcypher.com.")
            result = btc.get_btc_wallet_bal_blockcypher(args.wallet)
        elif args.blockchain_info:
            print(f"[-] Checking using Blockchain.info.")
            result = btc.get_btc_wallet_bal_blockchaininfo(args.wallet)
        else:
            print(f"[-] Checking using Bitref.com.")
            result = btc.get_btc_wallet_bal_bitref(args.wallet)
        if result.get('balance'):
            print(f"{Fore.LIGHTGREEN_EX}[$] Balance: {result.get('balance')}, Wallet: {result.get('wallet')}{Fore.RESET}")
        else:
            print(f"[-] Balance: {result.get('balance')}, Wallet: {result.get('wallet')}{Fore.RESET}")

        if args.output:
            btc.output_to_file([result])

    elif args.list:
        if args.blockcypher:
            print(f"[-] Checking using blockcypher.com.")
            results = btc.multi_wallet_lookup(args.list, 'blockcypher')
        elif args.blockchain_info:
            print(f"[-] Checking using Blockchain.info.")
            results = btc.multi_wallet_lookup(args.list, 'blockchain-info')
        else:
            print(f"[-] Checking using Bitref.com.")
            results = btc.multi_wallet_lookup(args.list, 'bitref')
        if args.output:
            btc.output_to_file(results)


if __name__ == "__main__":

    main()
