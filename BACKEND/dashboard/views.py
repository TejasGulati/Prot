import os
os.environ['GRPC_TRACE'] = 'none'
os.environ['GRPC_VERBOSITY'] = 'ERROR'

import google.generativeai as genai
from datetime import timedelta
from tokenize import TokenError
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import logout as django_logout
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count
from dashboard.models import Article, Bookmark, UserArticleView
from dashboard.serializers import ArticleSerializer, BookmarkSerializer
from users.serializers import UserSerializer
from django.shortcuts import get_object_or_404
import logging
import random
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
import requests
import logging
import json
from datetime import timedelta
import google.generativeai as genai
from django.utils import timezone
logger = logging.getLogger(__name__)

genai.configure(api_key="AIzaSyAsl-bfdt3awt49RrT8rSXl4ClLwyhBbKs")
ai_model = genai.GenerativeModel('gemini-pro')


class AIEnhancedView(APIView):
    permission_classes = [IsAuthenticated]
    
    def _generate_ai_content(self, prompt, max_attempts=3):
        for attempt in range(max_attempts):
            try:
                response = ai_model.generate_content(prompt)
                parsed_content = self._parse_ai_response(response.text)
                if parsed_content:
                    return parsed_content
            except Exception as e:
                logger.warning(f"AI content generation attempt {attempt + 1} failed: {str(e)}")
        
        logger.error(f"All {max_attempts} attempts to generate AI content failed.")
        return None

    def _parse_ai_response(self, response_text):
        try:
            cleaned_text = response_text.strip().strip('`')
            
            if cleaned_text.lower().startswith('json'):
                cleaned_text = cleaned_text[4:].lstrip()
            
            parsed_json = json.loads(cleaned_text)
            
            return self._clean_and_structure_json(parsed_json)
        except json.JSONDecodeError:
            logger.warning("Failed to parse AI response as JSON. Attempting to structure the raw text.")
            return self._structure_raw_text(cleaned_text)

    def _clean_and_structure_json(self, data):
        if isinstance(data, dict):
            return {self._clean_key(k): self._clean_and_structure_json(v) 
                    for k, v in data.items() if v is not None and v != ""}
        elif isinstance(data, list):
            return [self._clean_and_structure_json(item) 
                    for item in data if item is not None and item != ""]
        elif isinstance(data, str):
            return self._clean_text(data)
        else:
            return data

    @staticmethod
    def _clean_key(key):
        cleaned_key = ''.join(c.lower() if c.isalnum() else '_' for c in key)
        return '_'.join(word for word in cleaned_key.split('_') if word)

    def _clean_text(self, text):
        cleaned = text.replace('\\n', ' ').replace('\\', '').strip()
        return ' '.join(cleaned.split())

    def _structure_raw_text(self, text):
        lines = text.split('\n')
        structured_data = {}
        current_key = None
        current_list = None
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.endswith(':'):
                current_key = self._clean_key(line[:-1])
                structured_data[current_key] = {}
                current_list = None
            elif line.startswith('- '):
                if current_list is None:
                    current_list = []
                    structured_data[current_key] = current_list
                current_list.append(line[2:])
            elif ':' in line:
                key, value = line.split(':', 1)
                if current_key:
                    structured_data[current_key][self._clean_key(key)] = value.strip()
                else:
                    structured_data[self._clean_key(key)] = value.strip()
            else:
                if current_list is not None:
                    current_list[-1] += ' ' + line
                elif current_key:
                    last_subkey = list(structured_data[current_key].keys())[-1]
                    structured_data[current_key][last_subkey] += ' ' + line
                else:
                    structured_data[current_key] += ' ' + line
        return structured_data
    
class WeatherView(AIEnhancedView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        api_key = os.getenv("WEATHER_API_KEY")
        current_base_url = "http://api.openweathermap.org/data/2.5/weather"
        forecast_base_url = "http://api.openweathermap.org/data/2.5/forecast"
        air_pollution_base_url = "http://api.openweathermap.org/data/2.5/air_pollution"

        # Check if latitude and longitude are provided
        lat = request.query_params.get('lat')
        lon = request.query_params.get('lon')
        city = request.query_params.get('city')

        # Your existing parameter logic remains the same
        if lat and lon:
            current_params = {
                'lat': lat,
                'lon': lon,
                'appid': api_key,
                'units': 'metric'
            }
            forecast_params = {
                'lat': lat,
                'lon': lon,
                'appid': api_key,
                'units': 'metric'
            }
            air_pollution_params = {
                'lat': lat,
                'lon': lon,
                'appid': api_key
            }
        elif city:
            # Your existing city geocoding logic remains the same
            geocode_params = {
                'q': city,
                'appid': api_key,
                'units': 'metric'
            }
            geocode_response = requests.get(current_base_url, params=geocode_params)
            geocode_data = geocode_response.json()

            if geocode_response.status_code != 200 or "coord" not in geocode_data:
                return Response({"error": "Failed to geocode city name or city not found"},
                                status=geocode_response.status_code)

            lat = geocode_data["coord"]["lat"]
            lon = geocode_data["coord"]["lon"]
            current_params = {
                'lat': lat,
                'lon': lon,
                'appid': api_key,
                'units': 'metric'
            }
            forecast_params = {
                'lat': lat,
                'lon': lon,
                'appid': api_key,
                'units': 'metric'
            }
            air_pollution_params = {
                'lat': lat,
                'lon': lon,
                'appid': api_key
            }
        else:
            # Your existing default city logic remains the same
            current_params = {
                'q': 'New Delhi',
                'appid': api_key,
                'units': 'metric'
            }
            forecast_params = {
                'q': 'New Delhi',
                'appid': api_key,
                'units': 'metric'
            }
            air_pollution_params = {
                'lat': 28.6139,
                'lon': 77.2090,
                'appid': api_key
            }

        try:
            # Your existing API calls remain the same
            current_response = requests.get(current_base_url, params=current_params)
            current_data = current_response.json()

            if current_response.status_code != 200:
                return Response({"error": current_data.get("message", "Failed to fetch current weather data")},
                                status=current_response.status_code)

            forecast_response = requests.get(forecast_base_url, params=forecast_params)
            forecast_data = forecast_response.json()

            if forecast_response.status_code != 200:
                return Response({"error": forecast_data.get("message", "Failed to fetch forecast data")},
                                status=forecast_response.status_code)

            air_pollution_response = requests.get(air_pollution_base_url, params=air_pollution_params)
            air_pollution_data = air_pollution_response.json()

            if air_pollution_response.status_code != 200:
                return Response({"error": air_pollution_data.get("message", "Failed to fetch air pollution data")},
                                status=air_pollution_response.status_code)

            # Your existing forecast processing remains the same
            forecast_list = forecast_data["list"]
            filtered_forecast = []
            for entry in forecast_list[::8][:5]:
                filtered_forecast.append({
                    "date": entry["dt_txt"],
                    "temperature": entry["main"]["temp"],
                    "description": entry["weather"][0]["description"]
                })

            # Your existing weather_info structure remains the same
            weather_info = {
                "current": {
                    "city": current_data["name"],
                    "temperature": current_data["main"]["temp"],
                    "description": current_data["weather"][0]["description"],
                    "humidity": current_data["main"]["humidity"],
                    "wind_speed": current_data["wind"]["speed"],
                },
                "forecast": {
                    "city": forecast_data["city"]["name"],
                    "forecast_data": filtered_forecast
                },
                "air_pollution": {
                    "aqi": air_pollution_data["list"][0]["main"]["aqi"],
                    "components": air_pollution_data["list"][0]["components"]
                }
            }

            # Generate AI insights for the weather data
            ai_insights = self._generate_weather_insights(weather_info)

            # Add AI insights to the response
            weather_info["ai_insights"] = ai_insights

            return Response(weather_info, status=status.HTTP_200_OK)

        except requests.exceptions.RequestException as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def _generate_weather_insights(self, weather_data):
        try:
            # Calculate temperature category
            temp = weather_data['current']['temperature']
            temp_category = (
                "Freezing" if temp < 0 else
                "Cold" if temp < 10 else
                "Mild" if temp < 20 else
                "Warm" if temp < 30 else
                "Hot"
            )

            # Define AQI categories
            aqi_categories = {
                1: "Good",
                2: "Fair",
                3: "Moderate",
                4: "Poor",
                5: "Very Poor"
            }
            aqi_category = aqi_categories.get(weather_data['air_pollution']['aqi'], "Unknown")

            # Create structured prompt
            prompt = f"""
            Analyze the following weather data and return a JSON response exactly matching this structure:
            {{
                "weather_summary": {{
                    "current_conditions": string (50 words max describing current temperature, humidity, and wind),
                    "temperature_category": "{temp_category}",
                    "comfort_level": string (one of: "Very Comfortable", "Comfortable", "Moderate", "Uncomfortable", "Very Uncomfortable")
                }},
                "health_recommendations": {{
                    "outdoor_activity_score": integer (0-10),
                    "recommended_activities": list of 3 strings,
                    "health_risks": list of strings (provide at least one),
                    "precautions": list of strings (provide at least one)
                }},
                "air_quality_analysis": {{
                    "category": "{aqi_category}",
                    "main_pollutants": list of strings (based on PM2.5: {weather_data['air_pollution']['components']['pm2_5']} and PM10: {weather_data['air_pollution']['components']['pm10']}),
                    "health_impact": string (30 words max),
                    "recommended_actions": list of strings (provide at least one)
                }},
                "forecast_insights": {{
                    "temperature_trend": string (one of: "Rising", "Falling", "Stable"),
                    "weather_pattern": string (30 words max),
                    "notable_changes": list of strings (provide at least one),
                    "weekend_outlook": string (20 words max)
                }},
                "travel_recommendations": {{
                    "outdoor_activities_suitable": boolean,
                    "best_time_for_outdoors": string (one of: "Early Morning", "Morning", "Afternoon", "Evening", "Night", "Not Recommended"),
                    "clothing_suggestions": list of strings (provide at least one),
                    "travel_precautions": list of strings (provide at least one)
                }}
            }}

            Current conditions: Temperature: {temp}°C, Description: {weather_data['current']['description']}, 
            Humidity: {weather_data['current']['humidity']}%, Wind Speed: {weather_data['current']['wind_speed']} m/s

            Air Quality:
            - AQI: {weather_data['air_pollution']['aqi']}
            - PM2.5: {weather_data['air_pollution']['components']['pm2_5']} μg/m³
            - PM10: {weather_data['air_pollution']['components']['pm10']} μg/m³

            5-Day Forecast: {json.dumps(weather_data['forecast']['forecast_data'], indent=2)}

            Ensure all response values strictly follow the specified formats and types. Provide at least one item for each list, even if it's a general recommendation or observation.
            """

            ai_response = self._generate_ai_content(prompt)
            
            # Validate and fill any potentially missing keys
            validated_response = self._validate_and_fill_ai_response(ai_response)
            
            return validated_response
        except Exception as e:
            logger.error(f"Error generating weather insights: {str(e)}")
            return self._get_fallback_insights()

    def _validate_and_fill_ai_response(self, ai_response):
        default_values = {
            "weather_summary": {
                "current_conditions": "Weather conditions are currently unavailable.",
                "temperature_category": "Unknown",
                "comfort_level": "Moderate"
            },
            "health_recommendations": {
                "outdoor_activity_score": 5,
                "recommended_activities": ["Stay Indoors", "Check Weather Updates", "Plan Indoor Activities"],
                "health_risks": ["No Specific Risks Identified"],
                "precautions": ["Take General Health Precautions"]
            },
            "air_quality_analysis": {
                "category": "Unknown",
                "main_pollutants": ["Data Unavailable"],
                "health_impact": "Impact on health is currently unknown.",
                "recommended_actions": ["Follow Local Health Guidelines"]
            },
            "forecast_insights": {
                "temperature_trend": "Stable",
                "weather_pattern": "Weather pattern is currently unpredictable.",
                "notable_changes": ["No Significant Changes Noted"],
                "weekend_outlook": "Weekend weather outlook is uncertain."
            },
            "travel_recommendations": {
                "outdoor_activities_suitable": True,
                "best_time_for_outdoors": "Afternoon",
                "clothing_suggestions": ["Dress Appropriately for the Weather"],
                "travel_precautions": ["Check Local Weather Updates Before Traveling"]
            }
        }

        validated_response = ai_response.copy() if isinstance(ai_response, dict) else {}

        for category, values in default_values.items():
            if category not in validated_response:
                validated_response[category] = values
            else:
                for key, value in values.items():
                    if key not in validated_response[category] or not validated_response[category][key]:
                        validated_response[category][key] = value

            # Ensure lists have at least one item
            for key, value in validated_response[category].items():
                if isinstance(value, list) and not value:
                    validated_response[category][key] = [default_values[category][key][0]]

        return validated_response

    def _get_fallback_insights(self):
        return {
            "weather_summary": {
                "current_conditions": "Weather data is currently unavailable. Please check again later.",
                "temperature_category": "Unknown",
                "comfort_level": "Moderate"
            },
            "health_recommendations": {
                "outdoor_activity_score": 5,
                "recommended_activities": ["Indoor Activities", "Check Weather Updates", "Plan Accordingly"],
                "health_risks": ["Unable to Determine Specific Risks"],
                "precautions": ["Stay Informed About Local Weather Conditions"]
            },
            "air_quality_analysis": {
                "category": "Unknown",
                "main_pollutants": ["Data Unavailable"],
                "health_impact": "Unable to determine air quality impact on health.",
                "recommended_actions": ["Follow Local Air Quality Guidelines"]
            },
            "forecast_insights": {
                "temperature_trend": "Unknown",
                "weather_pattern": "Weather pattern information is currently unavailable.",
                "notable_changes": ["No Data Available for Changes"],
                "weekend_outlook": "Weekend forecast unavailable."
            },
            "travel_recommendations": {
                "outdoor_activities_suitable": True,
                "best_time_for_outdoors": "Unknown",
                "clothing_suggestions": ["Prepare for Variable Weather Conditions"],
                "travel_precautions": ["Check Weather Before Traveling", "Be Prepared for Changes"]
            }
        }

class DashboardView(APIView):
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        user = request.user
        if not user.is_authenticated:
            return Response({"error": "User not authenticated"}, status=status.HTTP_401_UNAUTHORIZED)
        serializer = UserSerializer(user)
        return Response({'message': 'Welcome to your dashboard!', 'user': serializer.data})


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 9
    page_size_query_param = 'page_size'
    max_page_size = 100

class ArticlesView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get(self, request, article_id=None):
        if article_id is not None:
            return self.retrieve_article(request, article_id)
        else:
            return self.list_articles(request)

    def retrieve_article(self, request, article_id):
        # Fetch a specific article by ID
        article = get_object_or_404(Article, id=article_id)

        # Check if the article has a valid media_url
        if not article.media_url:
            return Response({"error": "Article has no valid media URL"}, status=status.HTTP_404_NOT_FOUND)

        # Log the article view
        UserArticleView.objects.create(user=request.user, article=article)

        serializer = ArticleSerializer(article, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def list_articles(self, request):
        # Get the category from the query parameters
        category = request.query_params.get('category')

        # Fetch all articles or filter by category if provided
        queryset = Article.objects.filter(category=category) if category else Article.objects.all()

        # Filter articles based on content relevance
        filtered_articles = [
            article for article in queryset
            if article.content.strip() != 'No summary available' and
            len(article.title.split()) > 2 and
            article.media_url and
            self.is_content_relevant(article)
        ]

        # Sort articles by creation date (newest first)
        filtered_articles.sort(key=lambda x: x.created_at, reverse=True)

        # Paginate the results
        paginator = self.pagination_class()
        paginated_articles = paginator.paginate_queryset(filtered_articles, request)

        # Serialize and return paginated articles
        serializer = ArticleSerializer(paginated_articles, many=True, context={'request': request})
        return paginator.get_paginated_response(serializer.data)
    
    def is_content_relevant(self, article):
        # Example relevance check: content should include keywords from the title
        title_keywords = set(article.title.lower().split())
        content_keywords = set(article.content.lower().split())
        return any(keyword in content_keywords for keyword in title_keywords)

class UserArticleViewCountView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        view_count = UserArticleView.objects.filter(user=request.user).count()
        return Response({'view_count': view_count}, status=status.HTTP_200_OK)
class BookmarksView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Retrieve all bookmarks for the authenticated user
        bookmarks = Bookmark.objects.filter(user=request.user)
        serializer = BookmarkSerializer(bookmarks, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        # Add a new bookmark
        article_id = request.data.get('article_id')
        if not article_id:
            return Response({'error': 'Article ID is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            article = Article.objects.get(id=article_id)
        except Article.DoesNotExist:
            return Response({'error': 'Article not found'}, status=status.HTTP_404_NOT_FOUND)

        bookmark, created = Bookmark.objects.get_or_create(user=request.user, article=article)
        if not created:
            return Response({'message': 'Article already bookmarked'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = BookmarkSerializer(bookmark)

        # Remove the 'article' field from the serialized data
        bookmark_data = serializer.data
        if 'article' in bookmark_data:
            del bookmark_data['article']

        response_data = {
            'message': 'Bookmark saved successfully',
            'bookmark': bookmark_data
        }
        return Response(response_data, status=status.HTTP_201_CREATED)

    def delete(self, request, article_id=None):
        # Remove a bookmark
        if article_id is None:
            return Response({'error': 'Article ID is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            article = Article.objects.get(id=article_id)
        except Article.DoesNotExist:
            return Response({'error': 'Article not found'}, status=status.HTTP_404_NOT_FOUND)

        bookmark = Bookmark.objects.filter(user=request.user, article=article).first()
        if bookmark:
            bookmark.delete()
            return Response({'message': 'Bookmark removed'}, status=status.HTTP_204_NO_CONTENT)
        else:
            return Response({'error': 'Bookmark not found'}, status=status.HTTP_404_NOT_FOUND)


class BookmarkCountView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Count all bookmarks for the authenticated user
        bookmark_count = Bookmark.objects.filter(user=request.user).count()
        return Response({'bookmark_count': bookmark_count}, status=status.HTTP_200_OK)

class NotificationsView(APIView):
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        return Response({'message': 'Notifications list'})

class CommentsView(APIView):
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        return Response({'message': 'Comments list'})

class LogoutView(APIView):
    authentication_classes = [JWTAuthentication]

    def post(self, request):
        user = request.user
        if not user.is_authenticated:
            return Response({"error": "User not authenticated"}, status=status.HTTP_401_UNAUTHORIZED)

        django_logout(request)

        auth_header = request.headers.get('Authorization', None)
        if auth_header:
            try:
                token_type, token = auth_header.split(' ')
                if token_type.lower() != 'bearer':
                    return Response({"error": "Invalid token type"}, status=status.HTTP_400_BAD_REQUEST)

                access_token = AccessToken(token)
                # Implement token blacklisting or invalidation if needed
                # Example: access_token.blacklist()

            except TokenError as e:
                return Response({"error": f"Invalid token: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({"error": "Token required"}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"message": "Successfully logged out"}, status=status.HTTP_200_OK)

class RecommendedArticlesView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        # Count the user's bookmarks and article views
        bookmark_count = Bookmark.objects.filter(user=user).count()
        article_view_count = UserArticleView.objects.filter(user=user).count()

        if bookmark_count > 5 and article_view_count > 20:
            # Example logic for recommendations when criteria are met
            recent_views = UserArticleView.objects.filter(user=user).order_by('-viewed_at')[:5]
            viewed_articles = [view.article for view in recent_views]

            # Find articles that are not in the recently viewed list
            recommended_articles = Article.objects.exclude(id__in=[article.id for article in viewed_articles])

            # Filter articles based on content relevance
            filtered_articles = [
                article for article in recommended_articles
                if self.is_content_relevant(article)
            ]

            # Limit to top 3 articles
            top_recommended_articles = filtered_articles[:3]
        else:
            # Show 3 random articles if criteria are not met
            all_articles = Article.objects.all()
            filtered_articles = [
                article for article in all_articles
                if self.is_content_relevant(article)
            ]
            top_recommended_articles = random.sample(filtered_articles, min(3, len(filtered_articles)))

        serializer = ArticleSerializer(top_recommended_articles, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def is_content_relevant(self, article):
        # Example relevance check: content should include keywords from the title
        title_keywords = set(article.title.lower().split())
        content_keywords = set(article.content.lower().split())
        return any(keyword in content_keywords for keyword in title_keywords)

class TrendingArticlesView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        # Count the user's bookmarks and article views
        bookmark_count = Bookmark.objects.filter(user=user).count()
        article_view_count = UserArticleView.objects.filter(user=user).count()

        if bookmark_count > 5 and article_view_count > 20:
            # Trending articles based on view count in the last 30 days
            thirty_days_ago = timezone.now() - timedelta(days=30)
            trending_articles = Article.objects.filter(
                userarticleview__viewed_at__gte=thirty_days_ago
            ).annotate(view_count=Count('userarticleview')).order_by('-view_count')[:5]
        else:
            # Show 5 random articles if criteria are not met
            all_articles = Article.objects.all()
            filtered_articles = [
                article for article in all_articles
                if self.is_content_relevant(article)
            ]
            trending_articles = random.sample(filtered_articles, min(3, len(filtered_articles)))

        serializer = ArticleSerializer(trending_articles, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def is_content_relevant(self, article):
        # Example relevance check: content should include keywords from the title
        title_keywords = set(article.title.lower().split())
        content_keywords = set(article.content.lower().split())
        return any(keyword in content_keywords for keyword in title_keywords)
