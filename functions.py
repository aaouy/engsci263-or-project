import pandas as pd
from itertools import combinations
import numpy as np
from pulp import *
import math
import random
import folium

def create_routes(regions, distances_df, durations_df, noel_leeming_demand_est, warehouse_demand_est, distribution_north=False):
    routes_df = pd.DataFrame(columns=['Route', 'Demand', 'Distance', 'Driving Duration', 'Region']) # dataframe storing all routes
    for i in range(len(regions)):
        for j in range(1, len(regions[i])): # iterating over all combinations of routes within each region.
            routes = list(combinations(regions[i], j)) 
            for route in routes:
                route = list(route)
                demand = warehouse_demand_est if 'Warehouse' in route[0] else noel_leeming_demand_est
                distribution = 'Distribution South'
                if distribution_north and i + 1 in (3, 4): # if we are considering north dist, and we're considering region 3 or 4, then starting and ending distribution will be north dist.
                    distribution = 'Distribution North'
                distance = distances_df.loc[(distances_df['Origin'] == distribution) & (distances_df['Destination'] == route[0]), 'Distance'].iloc[0]
                duration = durations_df.loc[(durations_df['Origin'] == distribution) & (durations_df['Destination'] == route[0]), 'Duration'].iloc[0]
                for k in range(1, len(route)):
                    if 'Warehouse' in route[k]:
                        demand += warehouse_demand_est
                    else:
                        demand += noel_leeming_demand_est
    
                    if demand > 20: # if demand greater than 20, then route is infeasible so we don't include it.
                        break
                    
                    distance += distances_df.loc[(distances_df['Origin'] == route[k - 1]) & (distances_df['Destination'] == route[k]), 'Distance'].iloc[0]
                    duration += durations_df.loc[(durations_df['Origin'] == route[k - 1]) & (durations_df['Destination'] == route[k]), 'Duration'].iloc[0]
                    
                if demand <= 20:
                    distance += distances_df.loc[(distances_df['Origin'] == route[-1]) & (distances_df['Destination'] == distribution), 'Distance'].iloc[0]
                    duration += durations_df.loc[(durations_df['Origin'] == route[-1]) & (durations_df['Destination'] == distribution), 'Duration'].iloc[0]          
                    routes_df.loc[len(routes_df)] = [route, demand, distance, duration, i + 1]         
        
    return routes_df

def simulation_helper(current_shift_routes, current_shift_regions, next_shift_routes, next_shift_regions, nl_mu, nl_sd, warehouse_mu, warehouse_sd, warehouse_weekend_demand, durations_df, north_dist, is_weekend, cost):
    for index, route in enumerate(current_shift_routes):
        if index < 16: # iterating continues until our fleet size (16) is exceeded.
            demand, duration = 0, 0
            for j in range(len(route)):
                value = 0
                if 'Noel Leeming' in route[j]:
                    value = np.random.normal(nl_mu, nl_sd)
                elif 'Warehouse' in route[j] and is_weekend:
                    value = random.choice(warehouse_weekend_demand)
                else:
                    value = np.random.normal(warehouse_mu, warehouse_sd)
                demand += value
                if demand > 20:
                    duration += 10 * 60 * (demand - value)
                    next_shift_routes.append(route[j:]) # append the rest of the route to the next shift/wetlease if it is infeasible
                    next_shift_regions.append(current_shift_regions[index]) # append the respective region. 
                    route = route[:j]
                    break
                duration += 10 * 60 * value
            distribution = 'Distribution South'
            if current_shift_regions[index] in (3, 4) and north_dist:
                distribution = 'Distribution North'  
            duration += durations_df.loc[(durations_df['Origin'] == distribution) & (durations_df['Destination'] == route[0]), 'Duration'].iloc[0]
            for k in range(len(route) - 1):
                duration += durations_df.loc[(durations_df['Origin'] == route[k]) & (durations_df['Destination'] == route[k + 1]), 'Duration'].iloc[0]
            duration += durations_df.loc[(durations_df['Origin'] == route[-1]) & (durations_df['Destination'] == distribution), 'Duration'].iloc[0]
            cost += np.where(duration/3600 <= 4, (duration/3600) * 175, 4 * 175 + ((duration/3600) - 4) * 300) # calculation of cost of route
        else:
            for i in range(index, len(current_shift_routes)):
                next_shift_routes.append(current_shift_routes[i]) # if num of routes exceeds fleet, append the rest of the fleets to the next shift.
                next_shift_regions.append(current_shift_regions[i]) # append the respective region numbers.
            return cost
    return cost

def wet_lease_helper(wet_lease, wet_lease_regions, durations_df, nl_mu, nl_sd, warehouse_mu, warehouse_sd, warehouse_weekend_demand, north_dist, is_weekend, cost):
    for index, route in enumerate(wet_lease): # iterating over all routes that need to be wet leased.
        demand, duration = 0, 0
        for j in range(len(route)):
            if 'Noel Leeming' in route[j]:
                demand += np.random.normal(nl_mu, nl_sd)
            elif 'Warehouse' in route[j] and is_weekend:
                demand += random.choice(warehouse_weekend_demand)
            else:
                demand += np.random.normal(warehouse_mu, warehouse_sd)
            duration += 10 * 60 * demand
        distribution = 'Distribution South'
        if wet_lease_regions[index] in (3, 4) and north_dist:
            distribution = 'Distribution North'  
        duration += durations_df.loc[(durations_df['Origin'] == distribution) & (durations_df['Destination'] == route[0]), 'Duration'].iloc[0]
        for k in range(j):
            duration += durations_df.loc[(durations_df['Origin'] == route[k]) & (durations_df['Destination'] == route[k + 1]), 'Duration'].iloc[0]
        duration += durations_df.loc[(durations_df['Origin'] == route[-1]) & (durations_df['Destination'] == distribution), 'Duration'].iloc[0]
        cost += math.ceil((duration/3600)/4) * 1500 # wet lease cost.
    return cost

def simulation(current_shift_routes, current_shift_regions, durations_df, nl_mu, nl_sd, warehouse_mu, warehouse_sd, warehouse_weekend_demand, north_dist, is_weekend, n):
    res = np.zeros(n)
    for i in range(n):
        shift_two, wet_lease, shift_two_regions, wet_lease_regions = [], [], [], [] # routes and their respective regions that will in shift twoor wet leased.
        cost = simulation_helper(current_shift_routes, current_shift_regions, shift_two, shift_two_regions, nl_mu, nl_sd, warehouse_mu, warehouse_sd, warehouse_weekend_demand, durations_df, north_dist, is_weekend, 0)
        cost = simulation_helper(shift_two, shift_two_regions, wet_lease, wet_lease_regions, nl_mu, nl_mu, warehouse_mu, warehouse_sd, warehouse_weekend_demand, durations_df, north_dist, is_weekend, cost)
        cost = wet_lease_helper(wet_lease, wet_lease_regions, durations_df, nl_mu, nl_sd, warehouse_mu, warehouse_sd, warehouse_weekend_demand, north_dist, is_weekend, cost)
        res[i] = cost
    return res

def mapping(m, routes, optimal_routes, optimal_region, locations_df, client, is_north_dist):
    for i, route in enumerate(routes.loc[optimal_routes, 'Route']):
        temp = [locations_df.loc[locations_df['Store'] == 'Distribution North', 'Coordinates'].iloc[0] if optimal_region[i] in (3, 4) and is_north_dist else locations_df.loc[locations_df['Store'] == 'Distribution South', 'Coordinates'].iloc[0]]
        for j in range(len(route)):
            temp.append(locations_df.loc[locations_df['Store'] == route[j], 'Coordinates'].iloc[0])
        temp.append(locations_df.loc[locations_df['Store'] == 'Distribution North', 'Coordinates'].iloc[0] if optimal_region[i] in (3, 4) and is_north_dist else locations_df.loc[locations_df['Store'] == 'Distribution South', 'Coordinates'].iloc[0])
        route = client.directions(
            coordinates = temp,
            profile = 'driving-hgv',
            format = 'geojson', 
            validate = False
        )
        colors = 'green'
        if is_north_dist and optimal_region[i] in (3, 4):
            colors = 'blue'
        folium.PolyLine(locations=[list(reversed(coord)) for coord in route['features'][0]['geometry']['coordinates']], color = colors).add_to(m)
    