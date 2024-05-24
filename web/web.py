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
    
    def log(self, content):
        # pass
        with open('storage/log.txt', 'a') as file:
            file.write(content + "\r\n")

    async def get_json_response(self) -> Dict[Any, Any]:
       # read file response.json using aiofiles
       file_path = Path(os.path.dirname(__file__) , "response.json") 
       async with aiofiles.open(file_path.resolve(), mode="r") as f:
            return json.loads(await f.read())

    def paperIdsWithPdf(self, total_data):
        ids = []
       
        citations = total_data['citations']['data']
        references = total_data['references']['data']
       
        for item in citations:
            if(item["has_pdf"] and item["id"] not in ids):
                ids.append(item["id"])
        for item in references:
            if(item["has_pdf"] and item["id"] not in ids):
                ids.append(item["id"])

        return ids

    def extract_paper_details(self, details):
        authors = []
        year = 0
        numCiting = 0
        numCitedBy = 0

        try:
            for author in details['authors']:
                authors.append(author[0]['name'])
        except:
            authors = []
        
        try:
            year = details['year']
        except:
            year = 0

        try:
            numCiting = details['numCiting']
        except:
            numCiting = 0

        try:
            numCitedBy = details['numCitedBy']
        except:
            numCitedBy = 0

        temp_data = { 
            "id" : details['id'],
            "corpusId": details['corpusId'],
            "title": details['title']['text'],
            "slug": details['slug'],
            "venue": details['venue']['text'],
            "year": year,
            "authors": authors,
            "numCiting": numCiting,
            "numCitedBy": numCitedBy,
            "fieldsOfStudy": details['fieldsOfStudy'],
            "url" : "https://www.semanticscholar.org/paper/" + details['slug'] + "/" + details['id'],
            "has_pdf": details['isPdfVisible'],
            "pdf_url": "https://www.semanticscholar.org/reader/" + details['id']
        }
        if not details.get('isPdfVisible', False):
            del temp_data["pdf_url"]
        return temp_data
            
    def get_citations(self, paper_id, type):
        url = 'https://www.semanticscholar.org/api/1/search/paper/'+ paper_id + '/citations'  # Replace with your actual API endpoint
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
            citations.append(self.extract_paper_details(details))
        citations_count = citations_count + 1
        return citations

    def process_papers(self, paper_ids):
        
        start_time = time.time()

        paper_ids_with_pdf = []
        
        total_count = len(paper_ids.split(','))
        status_data = {
            "status": "working",
            "input": "Total " + str(total_count) + " hash IDs",
            "progress": "",
            "step": "Gathering Papers' Information",
            "elapsed": 0
        }
        status_data["progress"] = "started to gathering data..."
        with open('storage/paper/input.txt', 'w+') as input_file:
            input_file.truncate(0)
            input_file.write(paper_ids.replace(',', '\r\n'))

        with open('storage/paper/status.txt', 'w+') as file:
            file.truncate(0)
            file.write(json.dumps(status_data))
        
        data = {}
        index = 0

        with open('storage/paper/result.txt', 'w+') as result_file:
            result_file.truncate(0)

        with open('storage/paper/urls.txt', 'w+') as result_file:
            result_file.truncate(0)

        for paper_id in paper_ids.split(','):
            index += 1
            status_data['elapsed'] = self.getTimeDeltaInMinutes(start_time, time.time())
            status_data['status'] = 'working'
            status_data["progress"] = "Processing the " + str(index) + "th paper of " + str(total_count)
            
            with open('storage/paper/status.txt', 'w+') as file:
                file.truncate(0)
                file.write(json.dumps(status_data))
            
            try:
                # Get paper details 
                url = 'https://www.semanticscholar.org/api/1/paper/'+ paper_id
                response = requests.get(url, timeout=(5, 10))
                python_object = response.json()
                response_type = python_object['responseType']
                paper_details = {}
                if(response_type == 'PAPER_DETAIL'):
                    details = python_object['paper']
                    self.log("Getting paper details for the " + str(index) + "th paper...")
                    paper_details = self.extract_paper_details(details)
                    try:
                        paper_details['year'] = paper_details['year']['text']
                    except:
                        pass 
                    
                    if(paper_details["has_pdf"]):
                        paper_ids_with_pdf += [paper_id]
                
                # Get cited papers' information
                self.log("Getting citations data for the " + str(index) + "th paper...")
                citations_data = self.get_citations(paper_id, "citations")
                # Get reference papers' information
                self.log("Getting references data for the " + str(index) + "th paper...")
                reference_data = self.get_citations(paper_id, "references")
                
                paper_details['numCitedBy'] = len(citations_data)
                paper_details['citations'] = {
                    "total": len(citations_data),
                    "data": citations_data
                }
                
                paper_details['numCiting'] = len(reference_data)
                paper_details['references'] = {
                    "total": len(reference_data),
                    "data": reference_data
                }

                data[paper_id] = paper_details
                paper_ids_with_pdf += self.paperIdsWithPdf(paper_details)

            except requests.exceptions.Timeout:
                # content += (str(index) + "." + paper_id + ":" + "Timeout error\r\n")
                self.log('Timeout error occured')
                status_data['elapsed'] = self.getTimeDeltaInMinutes(start_time, time.time())
                status_data["status"] = "sleeping"
                status_data["progress"] = "Sleeping for 1.5 mins because timeout error occurs for the " + str(index) + 'th paper of ' + str(total_count)
                with open('storage/paper/status.txt', 'w+') as file:
                    file.truncate(0)
                    file.write(json.dumps(status_data))

                time.sleep(90)
            
            except requests.exceptions.RequestException as e:
                # content += (hash_value + ":" + "Network Error\r\n")
                self.log("Request exception occured")
                continue
            
            except:
                self.log('Other exception occured')


            # Write result to file 
            with open('storage/paper/result.txt', 'w+') as result_file:
                result_file.truncate(0)
                result_file.write(json.dumps(data))
        
        ################# Step 2: Getting pdf urls ####################
        status_data["step"] = "Getting pdf urls"
        
        #Get unique Paper Ids with PDF File
        paper_ids_with_pdf = list(set(paper_ids_with_pdf))
        paper_pdf_urls = [""] * len(paper_ids_with_pdf)
        
        index = 0
        total_count = len(paper_ids_with_pdf)
        
        urls = ""    

        try:
            for id in paper_ids_with_pdf:
                index += 1
                self.log(str(id) + ", index = " + str(index))
                self.log("going to start processing of the " + str(index) + " th file of " + str(total_count))
                status_data['elapsed'] = self.getTimeDeltaInMinutes(start_time, time.time())
                status_data['status'] = 'working'
                status_data["progress"] = "Getting url of the " + str(index) + "th paper of " + str(total_count)
                self.log("Getting url of the " + str(index) + "th paper of " + str(total_count) + " : paperId = " + str(id))
                with open('storage/paper/status.txt', 'w+') as file:
                    file.truncate(0)
                    file.write(json.dumps(status_data))

                try:
                    url = 'https://www.semanticscholar.org/api/1/paper/'+ id + '/pdf-data'  # Replace with your actual API endpoint
                    self.log("fetching paper pdf information: url = " + url)
                    response = requests.get(url, timeout=(5, 10))
                    self.log("fetched paper pdf information: url = " + url)
                    python_object = response.json()
                    pdf_url = ""
                    try:
                        pdf_url = python_object['pdfUrl']
                    except:
                        continue
                    self.log("before pdf_url = " + pdf_url)
                    paper_pdf_urls[index-1] = pdf_url
                    self.log("after pdf_url = " + pdf_url)
                    urls += (pdf_url + "\r\n")

                except requests.exceptions.Timeout:
                    self.log("Timeout error occured for the " + str(index) + "th paper of " + str(total_count))
                    status_data['elapsed'] = self.getTimeDeltaInMinutes(start_time, time.time())
                    status_data["status"] = "sleeping"
                    status_data["progress"] = "Sleeping for 1.5 mins because timeout error occurs for the " + str(index) + 'th paper of ' + str(total_count)
                    with open('storage/paper/status.txt', 'w+') as file:
                        file.truncate(0)
                        file.write(json.dumps(status_data))

                    time.sleep(90)
                    continue
                
                except requests.exceptions.RequestException as e:
                    self.log("RequestException error occured for the " + str(index) + "th paper of " + str(total_count))
                    time.sleep(90)
                    continue
                
                except:
                    self.log("Other exception error occured for the " + str(index) + "th paper of " + str(total_count))
                    time.sleep(90)
                    continue

                with open('storage/paper/urls.txt', 'w+') as urls_file:
                    urls_file.truncate(0)
                    urls_file.write(urls)

                self.log("finished processing of the " + str(index) + " th file of " + str(total_count))
        except:
            self.log("Unexpected error occured while getting pdf urls")
        
        self.log('Going to write urls')
        # Write final result to file 
        for key in data.keys():
            self.log("key = " + key + "")
            obj = data[key]
            try:
                if(obj['has_pdf']):
                    _index = paper_ids_with_pdf.index(key)
                    if(_index != -1):
                        obj['pdf_url'] = paper_pdf_urls[_index]
                for sub_paper in obj['citations']['data']:
                    if(sub_paper['has_pdf']):
                        _index1 = paper_ids_with_pdf.index(sub_paper['id'])
                        if(_index1 != -1):
                            sub_paper['pdf_url'] = paper_pdf_urls[_index1]
                for sub_paper in obj['references']['data']:
                    if(sub_paper['has_pdf']):
                        _index1 = paper_ids_with_pdf.index(sub_paper['id'])
                        if(_index1 != -1):
                            sub_paper['pdf_url'] = paper_pdf_urls[_index1]
            except:
                pass
                
        self.log('pacthed data')
        with open('storage/paper/result.txt', 'w+') as result_file:
            result_file.truncate(0)
            result_file.write(json.dumps(data))
         
        self.log('wrote final content to file')

        status_data["status"] = "finished"
        status_data["progress"] = "finished"
        status_data['elapsed'] = self.getTimeDeltaInMinutes(start_time, time.time())
        
        with open('storage/paper/status.txt', 'w+') as file:
            file.truncate(0)
            file.write(json.dumps(status_data))


    async def post_semantic_scholar(self, request: web.Request):
        data = await request.post()
        paper_ids =  data.get('hash_ids')
        with open('storage/paper/status.txt', 'r') as file:
            status_content = file.read()
            status_data = json.loads(status_content)
            if(status_data["status"] == "working"):
                return web.json_response({ "status": 0, "message": "cannot run this action because server is busy" })
            
        thread = threading.Thread(target=self.process_papers, name="paper-thread", args=(paper_ids, ))
        thread.start()
        
        total_count = len(paper_ids.split(','))
        return web.json_response({
            "status": "working",
            "input": "Total " + str(total_count) + " paper IDs",
            "progress": "processing 1th paper",
            "elapsed": 0,
        })
   
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
        with open('storage/paper/status.txt', 'r') as file:
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

    async def download_log_file(self, request: web.Request):
        # Path to the file to be downloaded
        file_path = 'storage/log.txt'
        
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

    async def clear_log_file(self, request: web.Request):
        # Path to the file to be downloaded
        file_path = 'storage/log.txt'

        with open(file_path, 'w+') as input_file:
            input_file.truncate(0)
            input_file.write('')
        
        return web.json_response({
            "status": "cleared logs"
        })
        
    async def download_paper_result_file(self, request: web.Request):
        # Path to the file to be downloaded
        file_path = 'storage/paper/result.txt'
        
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
            response.headers['Content-Disposition'] = f'attachment; filename="paper-informations.json"'
            
            return response
        
        except FileNotFoundError:
            return web.Response(text='File not found', status=404)
        
        except Exception as e:
            return web.Response(text=f'Error while reading the file: {e}', status=500)

    async def download_paper_result_urls(self, request: web.Request):
        # Path to the file to be downloaded
        file_path = 'storage/paper/urls.txt'
        
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
            response.headers['Content-Disposition'] = f'attachment; filename="paper-urls.txt"'
            
            return response
        
        except FileNotFoundError:
            return web.Response(text='File not found', status=404)
        
        except Exception as e:
            return web.Response(text=f'Error while reading the file: {e}', status=500)

    async def download_paper_input_file(self, request: web.Request):
        # Path to the file to be downloaded
        file_path = 'storage/paper/input.txt'
        
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
            response.headers['Content-Disposition'] = f'attachment; filename="paper-input-ids.txt"'
            
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
                    content += (url + "\r\n")
                else:
                    continue

            except requests.exceptions.Timeout:
                status_data['elapsed'] = self.getTimeDeltaInMinutes(start_time, time.time())
                status_data["status"] = "sleeping"
                status_data["progress"] = "Sleeping for 1.5 mins because timeout error occurs for the " + str(index) + 'th file of ' + str(total_count)
                with open('storage/code-book/status.txt', 'w+') as file:
                    file.truncate(0)
                    file.write(json.dumps(status_data))

                time.sleep(90)

            except requests.exceptions.RequestException as e:
                continue
            
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
                "progress": "processing 1th value",
                "elapsed": 0,
            })
            
    def _add_routes(self) -> None:
        self._web_app.router.add_route("GET", "/", self._get_json)
        self._web_app.router.add_route("GET", "/semantic_scholar", self.get_semantic_scholar)
        self._web_app.router.add_route("POST", "/semantic_scholar", self.post_semantic_scholar)
        self._web_app.router.add_route("GET", "/semantic_scholar/status", self.get_sematic_scholar_status)
        self._web_app.router.add_route("GET", "/paper/download-result", self.download_paper_result_file)
        self._web_app.router.add_route("GET", "/paper/download-urls", self.download_paper_result_urls)
        self._web_app.router.add_route("GET", "/paper/download-input", self.download_paper_input_file)
       
        self._web_app.router.add_route("GET", "/code-book", self.get_download_by_hash)
        self._web_app.router.add_route("POST", "/code-book", self.post_download_by_hash)
        self._web_app.router.add_route("GET", "/code-book/status", self.get_code_book_status)
        self._web_app.router.add_route("GET", "/code-book/download-result", self.download_book_result_file)
        self._web_app.router.add_route("GET", "/code-book/download-input", self.download_book_input_file)

        self._web_app.router.add_route("GET", "/download-log", self.download_log_file)
        self._web_app.router.add_route("POST", "/clear-log", self.clear_log_file)

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
