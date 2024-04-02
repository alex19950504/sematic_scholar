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
import time
import threading
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
            download_call = f"downloadPdf('{pdfUrl}', '{titles[index]}');  "
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

        for count in range(num_each_citations):
            details = python_object['results'][count]
            print(details)
            authors = []
            year = 0
            try:
                for author in details['authors']:
                    authors.append(author[0]['name'])
            except:
                authors = []
            
            try:
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

    def get_code_book_status(self, request: web.Request):
        with open('storage/code-book/status.txt', 'r') as file:
            status_content = file.read()
            status = json.loads(status_content)
        return web.json_response(status)
    
    def get_sematic_scholar_status(self, request: web.Request):
        with open('storage/paper/status.json', 'r') as file:
            status_content = file.read()
            status = json.loads(status_content)
        return web.json_response(status)

    async def download_book_result_file(self, request: web.Request):
        # Path to the file to be downloaded
        file_path = 'storage/code-book/result.txt'
        
        try:
            # Open the file for reading
            with open(file_path, 'rb') as file:
                # Read the file contents
                file_data = file.read()
            
            # Create an HTTP response with the file as the body
            response = web.Response(body=file_data)
            
            # Set the content type header
            response.headers['Content-Type'] = 'application/octet-stream'
            
            # Set the Content-Disposition header to force the browser to download the file
            response.headers['Content-Disposition'] = f'attachment; filename="gold-book-urls.txt"'
            
            return response
        
        except FileNotFoundError:
            return web.Response(text='File not found', status=404)
        
        except Exception as e:
            return web.Response(text=f'Error while reading the file: {e}', status=500)

    async def download_book_input_file(self, request: web.Request):
        # Path to the file to be downloaded
        file_path = 'storage/code-book/input.txt'
        
        try:
            # Open the file for reading
            with open(file_path, 'rb') as file:
                # Read the file contents
                file_data = file.read()
            
            # Create an HTTP response with the file as the body
            response = web.Response(body=file_data)
            
            # Set the content type header
            response.headers['Content-Type'] = 'application/octet-stream'
            
            # Set the Content-Disposition header to force the browser to download the file
            response.headers['Content-Disposition'] = f'attachment; filename="gold-book-input-hash-values.txt"'
            
            return response
        
        except FileNotFoundError:
            return web.Response(text='File not found', status=404)
        
        except Exception as e:
            return web.Response(text=f'Error while reading the file: {e}', status=500)

    def getTimeDeltaInMinutes(self, start_time, end_time):
        delta_seconds = end_time - start_time
        # Convert time delta to minutes
        delta_minutes = delta_seconds / 60
        return delta_minutes

    def process_books(self,hash_values):
        # set status as "working"
        
        start_time = time.time()
        
        total_count = len(hash_values.split(','))
        
        status_data = {
            "status": "working",
            "input": "Total " + str(total_count) + " hash IDs",
            "progress": "",
            "elapsed": 0
        }
        status_data["progress"] = "started to gathering data..."
        
        with open('storage/code-book/input.txt', 'w+') as input_file:
            input_file.truncate(0)
            input_file.write(hash_values.replace(',', '\r\n'))

        with open('storage/code-book/status.txt', 'w+') as file:
            file.truncate(0)
            file.write(json.dumps(status_data))
        
        index = 0
        
        with open('storage/code-book/result.txt', 'w+') as result_file:
            result_file.truncate(0)

        content = ""

        for hash_value in hash_values.split(','):
            index += 1
            status_data['elapsed'] = self.getTimeDeltaInMinutes(start_time, time.time())
            status_data['status'] = 'working'
            status_data["progress"] = "Processing the " + str(index) + "th file of " + str(total_count)
            
            with open('storage/code-book/status.txt', 'w+') as file:
                file.truncate(0)
                file.write(json.dumps(status_data))

            try:
                hash_url = f"https://library.lol/main/{hash_value}"
                response = requests.get(hash_url, timeout=(5, 10))
                files = response.text
                match = re.search(r'<a href="(https://cloudflare.*?)">Cloudflare', files)
                if match:
                    url = match.group(1)
                    content += (str(index) + "." + hash_value + ":" + url + "\r\n")
                else:
                    content += (str(index) + "." + hash_value + ":" + "Wrong hash\r\n")
            except requests.exceptions.Timeout:
                content += (str(index) + "." + hash_value + ":" + "Timeout error\r\n")
                
                status_data['elapsed'] = self.getTimeDeltaInMinutes(start_time, time.time())
                status_data["status"] = "sleeping"
                status_data["progress"] = "Sleeping for 1.5 mins because timeout error occurs for the " + str(index) + 'th file of ' + str(total_count)
                with open('storage/code-book/status.txt', 'w+') as file:
                    file.truncate(0)
                    file.write(json.dumps(status_data))

                time.sleep(90)

            except requests.exceptions.RequestException as e:
                content += (hash_value + ":" + "Network Error\r\n")
            
            # Write result to file 
            with open('storage/code-book/result.txt', 'w+') as result_file:
                result_file.truncate(0)
                result_file.write(content)

        status_data["status"] = "finished"
        status_data["progress"] = "finished"
        status_data['elapsed'] = self.getTimeDeltaInMinutes(start_time, time.time())

        with open('storage/code-book/status.txt', 'w+') as file:
            file.truncate(0)
            file.write(json.dumps(status_data))

    async def post_download_by_hash(self, request: web.Request):
        data = await request.post()
        hash_values =  data.get('hash_id')
        
        if hash_values is None:
            return web.json_response({ "status": 0, "message": "missing hash!" })
        else:
            with open('storage/code-book/status.txt', 'r') as file:
                status_content = file.read()
                status_data = json.loads(status_content)
                if(status_data["status"] == "working"):
                    return web.json_response({ "status": 0, "message": "cannot run this action because server is busy" })
            
            thread = threading.Thread(target=self.process_books, name="code-book-thread", args=(hash_values, ))
            thread.start()

            total_count = len(hash_values.split(','))
            return web.json_response({
                "status": "working",
                "input": "Total " + str(total_count) + " hash IDs",
                "progress": "processing 1th value"
            })
            
    def _add_routes(self) -> None:
        self._web_app.router.add_route("GET", "/", self._get_json)
        self._web_app.router.add_route("GET", "/semantic_scholar", self.get_semantic_scholar)
        self._web_app.router.add_route("POST", "/semantic_scholar", self.post_semantic_scholar)
        self._web_app.router.add_route("GET", "/code-book", self.get_download_by_hash)
        self._web_app.router.add_route("POST", "/code-book", self.post_download_by_hash)

        self._web_app.router.add_route("GET", "/code-book/status", self.get_code_book_status)
        self._web_app.router.add_route("GET", "/code-book/download-result", self.download_book_result_file)
        self._web_app.router.add_route("GET", "/code-book/download-input", self.download_book_input_file)

        self._web_app.router.add_route("GET", "/semantic_scholar/status", self.get_sematic_scholar_status)

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
