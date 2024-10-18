import { Component, OnInit } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { catchError, of } from 'rxjs';
import { animate, style, transition, trigger } from '@angular/animations';

interface WeatherData {
  current: {
    city: string;
    temperature: number;
    description: string;
    humidity: number;
    wind_speed: number;
  };
  forecast: {
    city: string;
    forecast_data: Array<{
      date: string;
      temperature: number;
      description: string;
    }>;
  };
  air_pollution: {
    aqi: number;
    components: {
      co: number;
      no: number;
      no2: number;
      o3: number;
      so2: number;
      pm2_5: number;
      pm10: number;
      nh3: number;
    };
  };
  ai_insights: {
    weather_summary: {
      current_conditions: string;
      temperature_category: string;
      comfort_level: string;
    };
    health_recommendations: {
      outdoor_activity_score: number;
      recommended_activities: string[];
      health_risks: string[];
      precautions: string[];
    };
    air_quality_analysis: {
      category: string;
      main_pollutants: string[];
      health_impact: string;
      recommended_actions: string[];
    };
    forecast_insights: {
      temperature_trend: string;
      weather_pattern: string;
      notable_changes: string[];
      weekend_outlook: string;
    };
    travel_recommendations: {
      outdoor_activities_suitable: boolean;
      best_time_for_outdoors: string;
      clothing_suggestions: string[];
      travel_precautions: string[];
    };
  };
}

@Component({
  selector: 'app-weather',
  templateUrl: './weather.component.html',
  styleUrls: ['./weather.component.css'],
  animations: [
    trigger('fadeInOut', [
      transition(':enter', [
        style({ opacity: 0, transform: 'translateY(20px)' }),
        animate('500ms ease-out', style({ opacity: 1, transform: 'translateY(0)' }))
      ]),
      transition(':leave', [
        animate('500ms ease-in', style({ opacity: 0, transform: 'translateY(-20px)' }))
      ])
    ])
  ]
})
export class WeatherComponent implements OnInit {
  city: string = '';
  weatherData?: WeatherData;
  error?: string;
  defaultCity: string = 'New York';
  isLoading: boolean = false;
  aiSections = [
    { key: 'weather_summary', title: 'Weather Summary', icon: 'cloud' },
    { key: 'health_recommendations', title: 'Health Recommendations', icon: 'favorite' },
    { key: 'air_quality_analysis', title: 'Air Quality Analysis', icon: 'air' },
    { key: 'forecast_insights', title: 'Forecast Insights', icon: 'timeline' },
    { key: 'travel_recommendations', title: 'Travel Recommendations', icon: 'luggage' }
  ];

  private apiUrl = 'http://127.0.0.1:8000/dashboard/weather';


  private descriptionToImage: { [key: string]: string } = {
    'clear sky': '1.png',
    'few clouds': '2.png',
    'scattered clouds': '3.png',
    'broken clouds': '4.png',
    'overcast clouds': '4.png',
    'shower rain': '5.png',
    'light rain': '6.png',
    'moderate rain': '7.png',
    'heavy intensity rain': '8.png',
    'very heavy rain': '8.png',
    'extreme rain': '8.png',
    'freezing rain': '9.png',
    'thunderstorm with light rain': '10.png',
    'thunderstorm with rain': '10.png',
    'thunderstorm with heavy rain': '10.png',
    'light thunderstorm': '10.png',
    'thunderstorm': '10.png',
    'heavy thunderstorm': '10.png',
    'ragged thunderstorm': '10.png',
    'thunderstorm with light drizzle': '10.png',
    'thunderstorm with drizzle': '10.png',
    'thunderstorm with heavy drizzle': '10.png',
    'light intensity drizzle': '11.png',
    'drizzle': '11.png',
    'heavy intensity drizzle': '11.png',
    'light intensity drizzle rain': '11.png',
    'drizzle rain': '11.png',
    'heavy intensity drizzle rain': '11.png',
    'shower rain and drizzle': '11.png',
    'heavy shower rain and drizzle': '11.png',
    'shower drizzle': '11.png',
    'light snow': '12.png',
    'snow': '12.png',
    'heavy snow': '12.png',
    'sleet': '12.png',
    'light shower sleet': '12.png',
    'shower sleet': '12.png',
    'light rain and snow': '12.png',
    'rain and snow': '12.png',
    'light shower snow': '12.png',
    'shower snow': '12.png',
    'heavy shower snow': '12.png',
    'mist': '13.png',
    'smoke': '14.png',
    'haze': '15.png',
    'dust': '16.png',
    'fog': '17.png',
    'sand': '18.png',
    'volcanic ash': '19.png',
    'squall': '20.png',
    'tornado': '21.png'
  };

  
  constructor(private http: HttpClient) {}

  ngOnInit(): void {
    this.fetchWeatherData();
  }

  private fetchWeatherData(): void {
    this.isLoading = true;
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        position => {
          const latitude = position.coords.latitude;
          const longitude = position.coords.longitude;
          this.getWeatherByCoordinates(latitude, longitude);
        },
        error => {
          console.error('Error getting location:', error);
          this.error = 'Unable to retrieve location. Showing default weather data.';
          this.getWeatherByCity(this.defaultCity);
        }
      );
    } else {
      this.error = 'Geolocation is not supported by this browser. Showing default weather data.';
      this.getWeatherByCity(this.defaultCity);
    }
  }

  private getWeatherByCoordinates(lat: number, lon: number): void {
    this.http.get<WeatherData>(`${this.apiUrl}/?lat=${lat}&lon=${lon}`)
      .pipe(
        catchError(err => {
          this.error = 'Failed to fetch weather data for your location.';
          console.error(err);
          return of(null);
        })
      )
      .subscribe(data => {
        this.isLoading = false;
        if (data) {
          this.weatherData = data;
          this.city = data.current.city;
          this.error = undefined;
        } else {
          this.weatherData = undefined;
        }
      });
  }

  private getWeatherByCity(city: string): void {
    this.http.get<WeatherData>(`${this.apiUrl}/?city=${city}`)
      .pipe(
        catchError(err => {
          this.error = 'Failed to fetch weather data.';
          console.error(err);
          return of(null);
        })
      )
      .subscribe(data => {
        this.isLoading = false;
        if (data) {
          this.weatherData = data;
          this.error = undefined;
        } else {
          this.weatherData = undefined;
        }
      });
  }

  searchWeather(): void {
    if (!this.city) {
      this.error = 'City name is required!';
      return;
    }

    this.isLoading = true;
    this.getWeatherByCity(this.city);
  }

  getWeatherImage(): string {
    if (!this.weatherData) {
      return 'assets/img/default.png';
    }
    const imageName = this.descriptionToImage[this.weatherData.current.description.toLowerCase()];
    return `assets/img/${imageName || 'default.png'}`;
  }

  getActivityScoreColor(score: number): string {
    if (score >= 8) return '#4CAF50';
    if (score >= 6) return '#8BC34A';
    if (score >= 4) return '#FFC107';
    if (score >= 2) return '#FF9800';
    return '#F44336';
  }
}