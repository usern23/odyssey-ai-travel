from __future__ import annotations
import logging
import math
from collections import defaultdict
from typing import List, Optional, Tuple
from src.components.travel_plan.domain.entities import Place
from src.components.travel_plan.application.tsp_solver import haversine_distance
logger = logging.getLogger(__name__)


class ClusterService:

    def cluster_by_location(self,
                            places: List[Place],
                            num_days: int,
                            hotel: Optional[Place] = None) -> List[List[Place]]:
        if not places:
            return [[] for _ in range(num_days)]
        if len(places) <= num_days:
            result = [[p] for p in places]
            while len(result) < num_days:
                result.append([])
            return result
        clusters = self._kmeans_cluster(places, num_days)
        clusters = self._balance_clusters(clusters)
        if hotel:
            clusters = self._sort_clusters_by_hotel(clusters, hotel)
        logger.debug(
            f'Created {len(clusters)} clusters from {len(places)} places')
        return clusters

    def _kmeans_cluster(self,
                        places: List[Place],
                        k: int,
                        max_iterations: int = 50) -> List[List[Place]]:
        if k <= 0:
            return [places]
        centroids = self._init_centroids_plusplus(places, k)
        clusters: List[List[Place]] = [[] for _ in range(k)]
        for iteration in range(max_iterations):
            clusters = [[] for _ in range(k)]
            for place in places:
                nearest_idx = self._find_nearest_centroid(place, centroids)
                clusters[nearest_idx].append(place)
            new_centroids = []
            for cluster in clusters:
                if cluster:
                    avg_lat = sum((p.lat for p in cluster)) / len(cluster)
                    avg_lon = sum((p.lon for p in cluster)) / len(cluster)
                    new_centroids.append((avg_lat, avg_lon))
                else:
                    new_centroids.append(centroids[len(new_centroids)] if len(
                        new_centroids) < len(centroids) else centroids[0])
            if new_centroids == centroids:
                break
            centroids = new_centroids
        clusters = [c for c in clusters if c]
        while len(clusters) < k:
            largest_idx = max(
                range(
                    len(clusters)), key=lambda i: len(
                    clusters[i]))
            largest = clusters[largest_idx]
            if len(largest) < 2:
                break
            mid = len(largest) // 2
            clusters[largest_idx] = largest[:mid]
            clusters.append(largest[mid:])
        return clusters

    def _init_centroids_plusplus(
            self, places: List[Place], k: int) -> List[Tuple[float, float]]:
        import random
        if not places:
            return []
        centroids = [(places[0].lat, places[0].lon)]
        for _ in range(k - 1):
            distances = []
            for place in places:
                min_dist = min(
                    (haversine_distance(
                        place.lat,
                        place.lon,
                        c[0],
                        c[1]) for c in centroids))
                distances.append(min_dist ** 2)
            total = sum(distances)
            if total == 0:
                break
            r = random.random() * total
            cumsum = 0
            for i, d in enumerate(distances):
                cumsum += d
                if cumsum >= r:
                    centroids.append((places[i].lat, places[i].lon))
                    break
        return centroids

    def _find_nearest_centroid(
            self, place: Place, centroids: List[Tuple[float, float]]) -> int:
        min_dist = float('inf')
        nearest_idx = 0
        for i, (lat, lon) in enumerate(centroids):
            dist = haversine_distance(place.lat, place.lon, lat, lon)
            if dist < min_dist:
                min_dist = dist
                nearest_idx = i
        return nearest_idx

    def _balance_clusters(self,
                          clusters: List[List[Place]],
                          max_diff: int = 2) -> List[List[Place]]:
        if not clusters:
            return clusters
        avg_size = sum((len(c) for c in clusters)) / len(clusters)
        for _ in range(10):
            sizes = [len(c) for c in clusters]
            if max(sizes) - min(sizes) <= max_diff:
                break
            largest_idx = sizes.index(max(sizes))
            smallest_idx = sizes.index(min(sizes))
            if largest_idx == smallest_idx:
                break
            large_cluster = clusters[largest_idx]
            small_cluster = clusters[smallest_idx]
            if not large_cluster:
                continue
            if small_cluster:
                small_center = (sum((p.lat for p in small_cluster)) /
                                len(small_cluster), sum((p.lon for p in small_cluster)) /
                                len(small_cluster))
            else:
                small_center = (sum((p.lat for p in large_cluster)) /
                                len(large_cluster), sum((p.lon for p in large_cluster)) /
                                len(large_cluster))
            closest_idx = min(
                range(
                    len(large_cluster)),
                key=lambda i: haversine_distance(
                    large_cluster[i].lat,
                    large_cluster[i].lon,
                    small_center[0],
                    small_center[1]))
            place = large_cluster.pop(closest_idx)
            small_cluster.append(place)
        return clusters

    def _sort_clusters_by_hotel(self,
                                clusters: List[List[Place]],
                                hotel: Place) -> List[List[Place]]:

        def cluster_distance(cluster: List[Place]) -> float:
            if not cluster:
                return float('inf')
            center_lat = sum((p.lat for p in cluster)) / len(cluster)
            center_lon = sum((p.lon for p in cluster)) / len(cluster)
            return haversine_distance(
                hotel.lat, hotel.lon, center_lat, center_lon)
        return sorted(clusters, key=cluster_distance)

    def cluster_with_time_budget(self,
                                 places: List[Place],
                                 num_days: int,
                                 hours_per_day: float = 8.0) -> List[List[Place]]:
        minutes_per_day = hours_per_day * 60
        geo_clusters = self.cluster_by_location(places, num_days)
        result = []
        overflow = []
        for cluster in geo_clusters:
            total_time = sum((p.visit_duration_min for p in cluster))
            if total_time <= minutes_per_day:
                result.append(cluster)
            else:
                sorted_places = sorted(
                    cluster, key=lambda p: p.visit_duration_min)
                day_places = []
                day_time = 0
                for place in sorted_places:
                    if day_time + place.visit_duration_min <= minutes_per_day:
                        day_places.append(place)
                        day_time += place.visit_duration_min
                    else:
                        overflow.append(place)
                result.append(day_places)
        for place in overflow:
            best_day_idx = -1
            best_time_left = 0
            for i, day in enumerate(result):
                day_time = sum((p.visit_duration_min for p in day))
                time_left = minutes_per_day - day_time
                if time_left >= place.visit_duration_min and time_left > best_time_left:
                    best_time_left = time_left
                    best_day_idx = i
            if best_day_idx >= 0:
                result[best_day_idx].append(place)
            else:
                shortest_idx = min(
                    range(
                        len(result)), key=lambda i: len(
                        result[i]))
                result[shortest_idx].append(place)
        return result
