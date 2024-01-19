import asyncio
import logging
import os
from typing import Tuple
import aiofiles
from aiohttp import web
from typing import Any, Dict
import urllib.parse
import requests
from pathlib import Path
import json
import numpy as np
import aiohttp
import re
logger = logging.getLogger(__name__)


class WebServer:
    def __init__(
        self,
        host: str,
        port: int,
    ):
        self._host = host
        self._port = port
        self._web_app = web.Application()
        self._runner = web.AppRunner(self._web_app)
        self._response_json = None

    async def get_json_response(self) -> Dict[Any, Any]:
       # read file response.json using aiofiles
       file_path = Path(os.path.dirname(__file__) , "response.json") 
       async with aiofiles.open(file_path.resolve(), mode="r") as f:
            return json.loads(await f.read())

    def get_pdf_url(self, paper_id):
        url = 'https://www.semanticscholar.org/api/1/paper/'+ paper_id + '/pdf-data'  # Replace with your actual API endpoint
        response = requests.get(url)
        python_object = response.json()
        return python_object['pdfUrl']
    
    def make_download_js_from_ids(self, paper_id, ids, titles, types):
        pdfUrls = []
        print(paper_id, ids, titles, types)
        dir = paper_id
        for idx, id in enumerate(ids):
            temp_url = self.get_pdf_url(id)
            print("Adding pdfUrl...")
            pdfUrls.append(temp_url)
        print(pdfUrls)
        #  Function to download the PDF file
        
        download_calls = []

        # Iterate over the pdfUrls list and format the downloadPdf function calls
        for index, pdfUrl in enumerate(pdfUrls):
            type = types[index]
            subdir = ""
            if type == 1:
                subdir = "citaions"
            elif type == 2:
                subdir = "references"
            download_call = f"downloadPdf('{pdfUrl}', '{dir}/{subdir}/{titles[index]}');  "
            print(download_call)
            download_calls.append(download_call)

        # Join the formatted downloadPdf function calls with a newline character
        concatenated_code = "\n".join(download_calls)
        
        final_code = concatenated_code
        # print("-----------final code--------")
        # print(final_code)
        return final_code
        
    def make_html_from_citations(self, paper_id, citations_data):
        ids = []
        titles = []
        types = []
       
        citations = citations_data['citations']['data']
        references = citations_data['references']['data']
       
        for item in citations:
            if(item["has_pdf"]):
                ids.append(item["id"])
                temp_title = item["title"].replace("'", "")
                titles.append(temp_title)
                types.append(1)
        for item in references:
            if(item["has_pdf"]):
                ids.append(item["id"])
                temp_title = item["title"].replace("'", "")
                titles.append(temp_title)
                types.append(2)
        jsCode = self.make_download_js_from_ids(paper_id, ids, titles, types)
        return jsCode

    def get_citations(self, paper_id, type):
        url = 'https://www.semanticscholar.org/api/1/search/paper/'+ paper_id + '/citations'  # Replace with your actual API endpoint
        # print(url)
        citationType = "citingPapers" if type == "citations" else "citedPapers"
        params = {
            'authors': [],
            'citationType': citationType,
            'coAuthors': [],
            'cues': ["CitedByLibraryPaperCue", "CitesYourPaperCue", "CitesLibraryPaperCue"],
            'fieldsOfStudy': [],
            'includePdfVisibility': True,
            'page': 1,
            'pageSize': 100,
            'requireViewablePdf': False,
            'sort': 'relevance',
            'venues': [],
            'yearFilter': None
        }
        response = requests.post(url, json=params)
        python_object = response.json()
        citations = []
        citations_count = 0
        num_each_citations = len(python_object['results'])
        print(python_object['results'])
        for count in range(num_each_citations):
            temp_data = { 
                "title": python_object['results'][count]['title']['text'],
                "id" : python_object['results'][count]['id'],
                # "authors" : python_object['results'][count]['authors'],
                # "year" : python_object['results'][count]['year'],
                "url" : "https://www.semanticscholar.org/paper/" + python_object['results'][count]['slug'] + "/" + python_object['results'][count]['id'],
                "has_pdf": python_object['results'][count]['isPdfVisible'],
                "pdf_url": "https://www.semanticscholar.org/reader/" + python_object['results'][count]['id']
            }
            if not python_object['results'][count].get('isPdfVisible', False):
                del temp_data["pdf_url"]
            citations.append(temp_data)
        citations_count = citations_count + 1
        return citations

    async def post_semantic_scholar(self, request: web.Request) -> Dict[Any, Any]:
        data = await request.post()
        hash_ids =  data.get('hash_ids')
        allow_download = data.get('allow_download')

        paper_id = request.query.get('paper_id')

        data = {}
        
        download_function = """
            async function downloadPdf(url, title) {
            try {
                const response = await fetch(url);
                const blob = await response.blob();
                const filename = title + ".pdf";
                const link = document.createElement("a");
                link.href = window.URL.createObjectURL(blob);
                link.download = filename;
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
            } catch (error) {
                console.error("Error downloading PDF:", error);
            }
            }

            // Call the downloadPdf function with the PDF file URL
        """

        for paper_id in hash_ids.split(','):
            citations_data = self.get_citations(paper_id, "citations")
            reference_data = self.get_citations(paper_id, "references")
            combined_data = {
                "citations": {
                    "total": len(citations_data),
                    "data": citations_data
                },
                "references": {
                    "total": len(reference_data),
                    "data": reference_data
                }
            }

            data[paper_id] = combined_data

            if allow_download == "1":
                download_function += self.make_html_from_citations(paper_id, combined_data)
        
        htmlCode = "<html><body><div id='demo'>" + json.dumps(data) + "</div></body><script>" + download_function + "</script></html>"
        return web.Response(text=htmlCode, content_type='text/html')
    def get_semantic_scholar(self, request: web.Request):
        with open('semantic-scholar.html', 'r') as file:
            html_content = file.read()
        return web.Response(text=html_content, content_type='text/html')

    def get_download_by_hash(self, request: web.Request):
        with open('code-book.html', 'r') as file:
            html_content = file.read()
        return web.Response(text=html_content, content_type='text/html')
    
    async def post_download_by_hash(self, request: web.Request):
        
        data = await request.post()
        hash_value =  data.get('hash_id')

        if hash_value is None:
            return web.Response(text="missing hash!")
        else:
            hash_url = f"https://library.lol/main/{hash_value}"
            response = requests.get(hash_url)
            files = response.text
            match = re.search(r'<a href="(https://cloudflare.*?)">Cloudflare', files)
            
            if match:
                url = match.group(1)
                # return web.Response(text=url)
                download_js = """
                 async function downloadPdf(url, title) {
                    try {
                        const response = await fetch(url);
                        const blob = await response.blob();
                        const filename = title + ".pdf";
                        const link = document.createElement("a");
                        link.href = window.URL.createObjectURL(blob);
                        link.download = filename;
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);
                    } catch (error) {
                        console.error("Error downloading PDF:", error);
                    }
                    }
                """
                download_code = f"downloadPdf('{url}', '{hash_value}');  "
                return web.Response(text="<html><body>pdf file will be downloaded soon....</body><script>" + download_js + download_code  + "</script></html>", content_type='text/html')
            else:
                return web.Response(text="wrong hash!")

    def _add_routes(self) -> None:
        self._web_app.router.add_route("GET", "/", self._get_json)
        self._web_app.router.add_route("GET", "/semantic_scholar", self.get_semantic_scholar)
        self._web_app.router.add_route("POST", "/semantic_scholar", self.post_semantic_scholar)
        self._web_app.router.add_route("GET", "/code-book", self.get_download_by_hash)
        self._web_app.router.add_route("POST", "/code-book", self.post_download_by_hash)
        self._web_app.router.add_route("HEAD", "/{tail:.*}", self._get_json)

    async def start_web_server(self) -> None:
        self._add_routes()
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port)
        self._response_json = await self.get_json_response()
        await site.start()

    async def _get_json(self, _request: web.Request) -> web.Response:
        with open('index.html', 'r') as file:
            html_content = file.read()
        return web.Response(text=html_content, content_type='text/html')

    async def close(self) -> None:
        await self._runner.cleanup()


def setup() -> Tuple[str, int]:
    try:
        host = os.environ["HOST"]
        logger.info("Host is %s", host)
    except KeyError:
        host = "0.0.0.0"
        logger.warning("Host was not provided via env. variable HOST, used %s", host)
    try:
        port = int(os.environ["PORT"])
        logger.info("Port is %s", port)
    except KeyError:
        port = 80
        logger.warning("Port was not provided via env. variable PORT, used %s", port)
    logger.info(f"Connect to http://%s:%s", host, port)
    return host, port


async def async_main() -> None:
    host, port = setup()
    web = WebServer(host, port)

    try:
        await web.start_web_server()
        while True:
            await asyncio.sleep(60)
    except KeyboardInterrupt:
        pass
    finally:
        await web.close()


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
