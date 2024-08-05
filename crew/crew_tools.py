import os
import requests
import datetime
import feedparser
from urllib.parse import quote_plus
from datetime import datetime, timedelta
from crewai_tools import BaseTool
from requests.exceptions import RequestException, Timeout
from typing import ClassVar, Dict
from pydantic import BaseModel
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from .config import entities, specific_keywords

# nltk.download('stopwords')
# nlp = spacy.load("en_core_web_sm")

class SophisticatedKeywordGeneratorTool(BaseTool):
    name: str = "SophisticatedKeywordGeneratorTool"
    description: str = "This tool generates specific keywords from a given high-level topic using advanced NLP techniques."

    def _run(self, topic: str) -> list:
        # Use spaCy to process the text
        # doc = nlp(topic)

        # Extract relevant noun chunks
        # noun_chunks = [chunk.text for chunk in doc.noun_chunks if chunk.text.lower() not in STOP_WORDS and ('oil' in chunk.text.lower() or 'gas' in chunk.text.lower())]

        # Use RAKE to extract keywords
        # rake = Rake()
        # rake.extract_keywords_from_text(topic)
        # rake_keywords = rake.get_ranked_phrases()

        # Combine all keywords
        all_keywords = entities

        # Add domain-specific keywords
        all_keywords += specific_keywords
        print("Keywords added!")

        # Deduplicate and filter keywords
        keywords = list(set(specific_keywords))
        keywords = [kw for kw in keywords if len(kw.split()) <= 3 and len(kw) > 2]
        print("Keywords filtered!")

        # Refine keywords to avoid unrelated topics
        # refined_keywords = [kw for kw in keywords if 'stock' not in kw or 'oil' in kw or 'gas' in kw]

        return keywords
    
# ------------------------------------------------------------------------------

class RSSFeedScraperTool(BaseTool):
    name: str = "RSSFeedScraperTool"
    description: str = ("This tool dynamically generates RSS feed URLs from keywords and "
                        "scrapes them to extract news articles. It returns a list of "
                        "articles with titles and links from the past week.")

    def _run(self, keywords_list: list) -> list:
        articles = []
        date_range = 3
        one_week_ago = datetime.datetime.now() - timedelta(days=date_range)

        for keyword in keywords_list:
            rss_url = f"https://news.google.com/rss/search?q={quote_plus(keyword)}+when:{date_range}d"
            feed = feedparser.parse(rss_url)
            keyword_article_count = 0
            for entry in feed.entries:
                published = datetime.datetime(*entry.published_parsed[:6])
                if published >= one_week_ago:
                    articles.append({
                        "Title": entry.title,
                        "Link": entry.link,
                        "Published": entry.published,
                    })
                    keyword_article_count += 1
            print(f"Keyword '{keyword}' added {keyword_article_count} articles")
        return articles

# ------------------------------------------------------------------------------

class SentimentAnalysisTool(BaseTool, BaseModel):
    name: str = "Sentiment Analysis Tool"
    description: str = "Reads news articles from a file and performs sentiment analysis."
    file_path: str = os.path.join(os.getcwd(), './Data/reports/sources/sources_ranked.json')

    def _run(self):
        # Read the file
        with open(self.file_path, 'r') as file:
            news_articles = file.read()

        # Split the file content into individual articles
        articles = news_articles.split('\n\n')  # Assuming each article is separated by two newlines

        # Perform sentiment analysis on each article
        results = []
        for article in articles:
            sentiment_score = self.perform_sentiment_analysis(article)
            sentiment = "positive" if sentiment_score > 0 else "negative"
            results.append({
                "article": article,
                "sentiment": sentiment
            })

        return results

    def perform_sentiment_analysis(self, article: str) -> float:
        analyzer = SentimentIntensityAnalyzer()
        sentiment_score = analyzer.polarity_scores(article)["compound"]
        return sentiment_score

    def __call__(self):
        return self._run()
    
# ------------------------------------------------------------------------------

class MarketAnalysisTool(BaseTool):
    name: str = "Market Analysis Tool"
    description: str = "Analyzes market trends for a given commodity."

    # Mapping of commodity names to Quandl database codes
    commodity_symbol_mapping: ClassVar[Dict[str, str]] = {
        "Brent": "CHRIS/ICE_B1",
        "WTI": "CHRIS/CME_CL1",
        "RBOB": "CHRIS/CME_RB1",
        "EBOB": "NSE/EBOP",
        "CBOB": "NSE/CBOP",
        "Singapore Gasoline R92": "SGX/FC03",
        "Europe Gasoil": "CHRIS/ICE_GASO",
        "Marine Gasoil 0.5% Singapore": "SGX/MGO",
        "Far East Index Propane": "EIA/PET_WCRSTUS1",
        "Far East Index Butane": "EIA/PET_WRBSTUS1",
        "Mt Belv Propane": "EIA/PET_RTPM_NUS_D",
        "Mt Belv Butane": "EIA/PET_RTBU_NUS_D",
        "ULSD New York": "EIA/PET_RMLS_NUS_D",
        "Asia Gasoil": "SGX/FOIL",
        "Marine Gasoil": "SGX/MGO",
        "Gold": "LBMA/GOLD",
        "Silver": "LBMA/SILVER"
    }

    def _run(self, commodity: str):
        # Fetch the correct code for the commodity
        code = self.commodity_symbol_mapping.get(commodity)
        if not code:
            return f"No code mapping found for {commodity}."

        # Fetching market data from Quandl API
        api_key = "ush97YpzsUyRTDZX8kWp"  # Quandl API key
        end_date = datetime.datetime.today().strftime('%Y-%m-%d')
        start_date = (datetime.datetime.today() - datetime.timedelta(days=30)).strftime('%Y-%m-%d')  # Last 30 days
        api_endpoint = f"https://www.quandl.com/api/v3/datasets/{code}/data.json?api_key={api_key}"

        try:
            response = requests.get(api_endpoint, timeout=10)  # Set a timeout for the request
            response.raise_for_status()  # Raise an error for bad status codes
            market_data = response.json()
            return self.analyze_market_data(commodity, market_data)
        except Timeout:
            return f"Request to Quandl API timed out for {commodity}."
        except RequestException as e:
            return f"An error occurred while fetching market data for {commodity}: {e}"

    def analyze_market_data(self, commodity: str, market_data: Dict):
        data = market_data.get("dataset_data", {}).get("data", [])
        if not data:
            return "No data available for analysis."

        latest_data = data[0]
        price = latest_data[1]  # Assuming the price is the second element in the data array
        prices = [entry[1] for entry in data]
        moving_average = self.calculate_moving_average(prices)

        if price > moving_average:
            trend = "bullish"
        else:
            trend = "bearish"

        # Dummy sentiment analysis (replace with actual sentiment analysis)
        # sentiment_analysis = "positive" if price > moving_average else "negative"

        analysis = {
            "commodity": commodity,
            "currentPrice": price,
            "movingAverage": moving_average,
            "trend": [ trend ]
        }

        return analysis

    def calculate_moving_average(self, prices: list, window: int = 20) -> float:
        if len(prices) < window:
            return sum(prices) / len(prices)
        return sum(prices[:window]) / window

    def __call__(self, commodity: str) -> str:
        return self._run(commodity)
    
market_analysis_tool = MarketAnalysisTool()

# class TavilyAPI(BaseTool):
#     name: str = "TavilyAPI"
#     description: str = ("The best search engine to use. If you want to search for anything, USE IT! "
#                         "Make sure your queries are very specific or else you will "
#                         "get websites that have the same content and that will waste your time.")

#     _client: TavilyClient = PrivateAttr()

#     def __init__(self, api_key: str):
#         super().__init__()
#         self._client = TavilyClient(api_key=api_key)

#     def _run(self, query: str) -> list:
#         response = self._client.search(query=query, search_depth='basic', max_results=10)
#         results = [{"Link": result["url"], "Title": result["title"]} for result in response["results"]]
#         return results

class FileReadTool_(BaseTool):
    name: str = "Read a file's content"
    description: str = "A tool that can be used to read a file's content."

    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path

    def _run(self) -> str:
        with open(self.file_path, 'r') as f:
            content = f.read()
        return content
    
class ReadCachetool(BaseTool):
    name : str="Readtool"
    description : str="Use it to read results of economic researchers!"

    def __init__(self, cache: list):
        super().__init__()
        self.cache = cache

    def _run(self)->list:
        return self.cache