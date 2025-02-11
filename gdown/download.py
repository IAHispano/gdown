from __future__ import print_function


import os
import os.path as osp
import re
import shutil
import sys
import tempfile
import textwrap
import time

import requests
import six
import tqdm
import bs4

from ._indent import indent
from .exceptions import FileURLRetrievalError
from .parse_url import parse_url
from http.cookiejar import MozillaCookieJar
CHUNK_SIZE = 512 * 1024  # 512KB
home = osp.expanduser("~")


def get_url_from_gdrive_confirmation(contents):
    url = ""
    m = re.search(r'href="(\/uc\?export=download[^"]+)', contents)
    if m:
        url = "https://docs.google.com" + m.groups()[0]
        url = url.replace("&amp;", "&")
        return url

    m = re.search(r'<input\s+type="hidden"\s+name="id"\s+value="([^"]+)"', contents)
    if m:
        url = m.groups()[0]
        uuid = re.search(r'<input\s+type="hidden"\s+name="uuid"\s+value="([^"]+)"', contents)
        uuid = uuid.groups()[0]
        m_ = re.search(r'<input\s+type="hidden"\s+name="at"\s+value="([^"]+)"', contents)
        url = "https://drive.usercontent.google.com/download?id=" + url + "&export=download&authuser=0&confirm=t&uuid=" + uuid
        if m_:
            at = m_.groups()[0]
            url = url + "&at=" + at
        return url
    
    soup = bs4.BeautifulSoup(contents, features="html.parser")
    form = soup.select_one("#download-form")
    if form is not None:
        url = form["action"].replace("&amp;", "&")
        url_components = six.moves.urllib_parse.urlsplit(url)
        query_params = six.moves.urllib_parse.parse_qs(url_components.query)
        for param in form.findChildren("input", attrs={"type": "hidden"}):
            query_params[param["name"]] = param["value"]
        query = six.moves.urllib_parse.urlencode(query_params, doseq=True)
        url = six.moves.urllib_parse.urlunsplit(url_components._replace(query=query))
        return url
    
    m = re.search(r'"downloadUrl":"([^"]+)', contents)
    if m:
        url = m.groups()[0]
        url = url.replace("\\u003d", "=")
        url = url.replace("\\u0026", "&")
        return url

    m = re.search(r'<p class="uc-error-subcaption">(.*)</p>', contents)
    if m:
        error = m.groups()[0]
        raise FileURLRetrievalError(error)

    raise FileURLRetrievalError(
        "Cannot retrieve the public link of the file. "
        "You may need to change the permission to "
        "'Anyone with the link', or have had many accesses."
    )


def _get_session(proxy, use_cookies, user_agent, return_cookies_file=False):
    sess = requests.session()

    sess.headers.update({"User-Agent": user_agent})

    if proxy is not None:
        sess.proxies = {"http": proxy, "https": proxy}
        print("Using proxy:", proxy, file=sys.stderr)

    # Load cookies if exists
    cookies_file = osp.join(home, ".cache/gdown/cookies.txt")
    if use_cookies and osp.exists(cookies_file):
        cookie_jar = MozillaCookieJar(cookies_file)
        cookie_jar.load()
        sess.cookies.update(cookie_jar)

    if return_cookies_file:
        return sess, cookies_file
    else:
        return sess


def download(
    url=None,
    output=None,
    quiet=True,
    proxy=None,
    speed=None,
    use_cookies=True,
    verify=True,
    id=None,
    fuzzy=False,
    resume=False,
    format=None,
    user_agent=None,
    log_messages=None,
):
    """Download file from URL.

    Parameters
    ----------
    url: str
        URL. Google Drive URL is also supported.
    output: str
        Output filename. Default is basename of URL.
    quiet: bool
        Suppress terminal output. Default is False.
    proxy: str
        Proxy.
    speed: float
        Download byte size per second (e.g., 256KB/s = 256 * 1024).
    use_cookies: bool
        Flag to use cookies. Default is True.
    verify: bool or string
        Either a bool, in which case it controls whether the server's TLS
        certificate is verified, or a string, in which case it must be a path
        to a CA bundle to use. Default is True.
    id: str
        Google Drive's file ID.
    fuzzy: bool
        Fuzzy extraction of Google Drive's file Id. Default is False.
    resume: bool
        Resume the download from existing tmp file if possible.
        Default is False.
    format: str, optional
        Format of Google Docs, Spreadsheets and Slides. Default is:
            - Google Docs: 'docx'
            - Google Spreadsheet: 'xlsx'
            - Google Slides: 'pptx'
    user_agent: str, optional
        User-agent to use in the HTTP request.
    log_messages: dict, optional
        Log messages to customize. Currently it supports:
        - 'start': the message to show the start of the download
        - 'output': the message to show the output filename

    Returns
    -------
    output: str
        Output filename.
    """
    if not (id is None) ^ (url is None):
        raise ValueError("Either url or id has to be specified")
    if id is not None:
        url = "https://drive.google.com/uc?id={id}".format(id=id)

    if user_agent is None:
        user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/39.0.2171.95 Safari/537.36"  # NOQA: E501

    if log_messages is None:
        log_messages = {}

    url_origin = url

    sess, cookies_file = _get_session(
        proxy=proxy,
        use_cookies=use_cookies,
        user_agent=user_agent,
        return_cookies_file=True,
    )

    gdrive_file_id, is_gdrive_download_link = parse_url(url, warning=not fuzzy)

    if fuzzy and gdrive_file_id:
        # overwrite the url with fuzzy match of a file id
        url = "https://drive.google.com/uc?id={id}".format(id=gdrive_file_id)
        url_origin = url
        is_gdrive_download_link = True

    while True:
        res = sess.get(url, stream=True, verify=verify)

        if url == url_origin and res.status_code == 500:
            # The file could be Google Docs or Spreadsheets.
            url = "https://drive.google.com/open?id={id}".format(
                id=gdrive_file_id
            )
            continue

        if res.headers["Content-Type"].startswith("text/html"):
            m = re.search("<title>(.+)</title>", res.text)
            if m and m.groups()[0].endswith(" - Google Docs"):
                url = (
                    "https://docs.google.com/document/d/{id}/export"
                    "?format={format}".format(
                        id=gdrive_file_id,
                        format="docx" if format is None else format,
                    )
                )
                continue
            elif m and m.groups()[0].endswith(" - Google Sheets"):
                url = (
                    "https://docs.google.com/spreadsheets/d/{id}/export"
                    "?format={format}".format(
                        id=gdrive_file_id,
                        format="xlsx" if format is None else format,
                    )
                )
                continue
            elif m and m.groups()[0].endswith(" - Google Slides"):
                url = (
                    "https://docs.google.com/presentation/d/{id}/export"
                    "?format={format}".format(
                        id=gdrive_file_id,
                        format="pptx" if format is None else format,
                    )
                )
                continue
        elif (
            "Content-Disposition" in res.headers
            and res.headers["Content-Disposition"].endswith("pptx")
            and format not in {None, "pptx"}
        ):
            url = (
                "https://docs.google.com/presentation/d/{id}/export"
                "?format={format}".format(
                    id=gdrive_file_id,
                    format="pptx" if format is None else format,
                )
            )
            continue

        if use_cookies:
            cookie_jar = MozillaCookieJar(cookies_file)
            for cookie in sess.cookies:
                cookie_jar.set_cookie(cookie)
            cookie_jar.save()

        if "Content-Disposition" in res.headers:
            # This is the file
            break
        if not (gdrive_file_id and is_gdrive_download_link):
            break

        # Need to redirect with confirmation
        try:
            url = get_url_from_gdrive_confirmation(res.text)
        except FileURLRetrievalError as e:
            message = (
                "Failed to retrieve file url:\n\n{}\n\n"
                "You may still be able to access the file from the browser:"
                "\n\n\t{}\n\n"
                "but Gdown can't. Please check connections and permissions."
            ).format(
                indent("\n".join(textwrap.wrap(str(e))), prefix="\t"),
                url_origin,
            )
            raise FileURLRetrievalError(message)

    if gdrive_file_id and is_gdrive_download_link:
        content_disposition = six.moves.urllib_parse.unquote(
            res.headers["Content-Disposition"]
        )
        m = re.search(r"filename\*=UTF-8''(.*)", content_disposition)
        if not m:
            m = re.search(r'filename=["\']?(.*?)["\']?$', content_disposition)
        filename_from_url = m.groups()[0]
        filename_from_url = filename_from_url.replace(osp.sep, "_")
    else:
        filename_from_url = osp.basename(url)

    if output is None:
        output = filename_from_url

    output_is_path = isinstance(output, six.string_types)
    if output_is_path and output.endswith(osp.sep):
        if not osp.exists(output):
            os.makedirs(output)
        output = osp.join(output, filename_from_url)

    if output_is_path:
        existing_tmp_files = []
        for file in os.listdir(osp.dirname(output) or "."):
            if file.startswith(osp.basename(output)):
                existing_tmp_files.append(osp.join(osp.dirname(output), file))
        if resume and existing_tmp_files:
            if len(existing_tmp_files) != 1:
                print(
                    "There are multiple temporary files to resume:",
                    file=sys.stderr,
                )
                print("\n")
                for file in existing_tmp_files:
                    print("\t", file, file=sys.stderr)
                print("\n")
                print(
                    "Please remove them except one to resume downloading.",
                    file=sys.stderr,
                )
                return
            tmp_file = existing_tmp_files[0]
        else:
            resume = False
            # mkstemp is preferred, but does not work on Windows
            # https://github.com/wkentaro/gdown/issues/153
            tmp_file = tempfile.mktemp(
                suffix=tempfile.template,
                prefix=osp.basename(output),
                dir=osp.dirname(output),
            )
        f = open(tmp_file, "ab")
    else:
        tmp_file = None
        f = output

    if tmp_file is not None and f.tell() != 0:
        headers = {"Range": "bytes={}-".format(f.tell())}
        res = sess.get(url, headers=headers, stream=True, verify=verify)

    if not quiet:
        print(log_messages.get("start", "Downloading...\n"), file=sys.stderr, end="")
        if resume:
            print("Resume:", tmp_file, file=sys.stderr)
        if url_origin != url:
            print("From (original):", url_origin, file=sys.stderr)
            print("From (redirected):", url, file=sys.stderr)
        else:
            print("From:", url, file=sys.stderr)
        print(
            log_messages.get(
                "output", f"To: {osp.abspath(output) if output_is_path else output}\n"
            ),
            file=sys.stderr,
            end="",
        )

    try:
        total = res.headers.get("Content-Length")
        if total is not None:
            total = int(total)
        if not quiet:
            pbar = tqdm.tqdm(total=total, unit="B", unit_scale=True)
        t_start = time.time()
        for chunk in res.iter_content(chunk_size=CHUNK_SIZE):
            f.write(chunk)
            if not quiet:
                pbar.update(len(chunk))
            if speed is not None:
                elapsed_time_expected = 1.0 * pbar.n / speed
                elapsed_time = time.time() - t_start
                if elapsed_time < elapsed_time_expected:
                    time.sleep(elapsed_time_expected - elapsed_time)
        if not quiet:
            pbar.close()
        if tmp_file:
            f.close()
            shutil.move(tmp_file, output)
    finally:
        sess.close()

    return output
