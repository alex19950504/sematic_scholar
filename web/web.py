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
import ssl
logger = logging.getLogger(__name__)


class WebServer:

    ssl_certfile = 'server.crt'
    ssl_keyfile = 'server.key'

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

    def get_pdf_url(self, request: web.Request):
        paper_id = request.query.get('paper_id')

        try:
            url = 'https://www.semanticscholar.org/api/1/paper/'+ paper_id + '/pdf-data'  # Replace with your actual API endpoint
            response = requests.get(url)
            python_object = response.json()
            return web.json_response({ "status": 1, "url": python_object['pdfUrl'] })
        except:
            return web.json_response({ "status": 0, "message": "Cannot find pdf link" })

    def make_download_js_from_ids(self, paper_id, ids, titles, types):
        pdfUrls = []
        print(paper_id, ids, titles, types)
        dir = paper_id
        for idx, id in enumerate(ids):
            temp_url = self.get_pdf_url(id)
            if temp_url:
                print("Adding pdfUrl...")
                pdfUrls.append(temp_url)
        print(pdfUrls)
        #  Function to download the PDF file
        
        return pdfUrls
        
    def make_html_from_citations(self, paper_id, citations_data):
        ids = []
        titles = []
        types = []
       
        citations = citations_data['citations']['data']
        references = citations_data['references']['data']
       
        for item in citations:
            if(item["has_pdf"] and item["id"] not in ids):
                ids.append(item["id"])
                temp_title = item["title"].replace("'", "")
                titles.append(temp_title)
                types.append(1)
        for item in references:
            if(item["has_pdf"] and item["id"] not in ids):
                ids.append(item["id"])
                temp_title = item["title"].replace("'", "")
                titles.append(temp_title)
                types.append(2)

        return ids
        # jsCode = self.make_download_js_from_ids(paper_id, ids, titles, types)
        # return jsCode
    
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
        for count in range(num_each_citations):
            details = python_object['results'][count]
            print(details)
            authors = []
            year = 0
            try:
                print(details['authors'])
                for author in details['authors']:
                    authors.append(author[0]['name'])
            except:
                authors = []
            
            try:
                print(details['year'])
                year = details['year']
            except:
                year = 0

            temp_data = { 
                "id" : details['id'],
                "corpusId": details['corpusId'],
                "title": details['title']['text'],
                "slug": details['slug'],
                "venue": details['venue']['text'],
                "year": year,
                "authors": authors,
                "numCiting": details['numCiting'],
                "numCitedBy": details['numCitedBy'],
                "fieldsOfStudy": details['fieldsOfStudy'],
                "url" : "https://www.semanticscholar.org/paper/" + python_object['results'][count]['slug'] + "/" + python_object['results'][count]['id'],
                "has_pdf": python_object['results'][count]['isPdfVisible'],
                "pdf_url": "https://www.semanticscholar.org/reader/" + python_object['results'][count]['id']
            }
            if not python_object['results'][count].get('isPdfVisible', False):
                del temp_data["pdf_url"]
            citations.append(temp_data)
        citations_count = citations_count + 1
        return citations

    async def post_semantic_scholar(self, request: web.Request):
        try:
            hash_ids = request.query.get("hash_ids")

            data = {}
            
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

                paper_ids_with_pdf = self.make_html_from_citations(paper_id, combined_data)
            return web.json_response({ "data": combined_data, "paper_ids_with_pdf":  paper_ids_with_pdf, "status": 1})
        except:
            return web.json_response({"status": 0})
            
    def get_semantic_scholar(self, request: web.Request):
        with open('semantic-scholar.html', 'r') as file:
            html_content = file.read()
        return web.Response(text=html_content, content_type='text/html')

    def get_download_by_hash(self, request: web.Request):
        with open('code-book.html', 'r') as file:
            html_content = file.read()
        return web.Response(text=html_content, content_type='text/html')
    
    async def post_download_by_hash(self, request: web.Request):
        
        hash_value = request.query.get("hash_id")

        if hash_value is None:
            return web.json_response({ "status":  0, "message": "Missing hash_id"})
        else:
            hash_url = f"https://library.lol/main/{hash_value}"
            response = requests.get(hash_url)
            files = response.text
            match = re.search(r'<a href="(https://cloudflare.*?)">Cloudflare', files)
            
            if match:
                url = match.group(1)
                return web.json_response({ "status": 1, "url": url })
            else:
                return web.json_response({ "status":  0, "message": "Wrong hash"})
            
    def _add_routes(self) -> None:
        self._web_app.router.add_route("GET", "/", self._get_json)
        self._web_app.router.add_route("GET", "/semantic_scholar", self.get_semantic_scholar)
        self._web_app.router.add_route("GET", "/scholar", self.post_semantic_scholar)
        self._web_app.router.add_route("GET", "/code-book", self.get_download_by_hash)
        self._web_app.router.add_route("GET", "/book", self.post_download_by_hash)
        self._web_app.router.add_route("GET", "/paper_link", self.get_pdf_url)
        self._web_app.router.add_route("HEAD", "/{tail:.*}", self._get_json)

    async def start_web_server(self) -> None:
        self._add_routes()
        await self._runner.setup()
         # Create an SSL context
        # ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        # ssl_context.load_cert_chain(self.ssl_certfile, self.ssl_keyfile)

        # site = web.TCPSite(self._runner, self._host, self._port, ssl_context=ssl_context)
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
