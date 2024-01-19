import random
import csv
import numpy as np
import concurrent.futures
from functools import partial
import numba
import pdb

import settings
import report

# Globals! (not really)
#base_infectivity = 0.000002
#settings.base_infectivity = 0.00001
settings.base_infectivity = 0.0001

def load( pop_file ):
    """
    Load population from csv file as np arrays. Each property column is an np array.
    """
    # Load the entire CSV file into a NumPy array
    header_row = np.genfromtxt(pop_file, delimiter=',', dtype=str, max_rows=1)

    # Load the remaining data as numerical values, skipping the header row
    data = np.genfromtxt(pop_file, delimiter=',', dtype=float, skip_header=1)

    # Extract headers from the header row
    headers = header_row

    # Load each column into a separate NumPy array
    columns = {header: data[:, i] for i, header in enumerate(headers)}
    columns['infected'] = columns['infected'].astype(bool)
    columns['immunity'] = columns['immunity'].astype(bool)
    columns['node'] = columns['node'].astype(np.uint32)
    columns['infection_timer'] = columns['infection_timer'].astype(np.float32) # int better?
    columns['incubation_timer'] = columns['incubation_timer'].astype(np.float32) # int better?
    columns['immunity_timer'] = columns['immunity_timer'].astype(np.float32) # int better?
    columns['age'] = columns['age'].astype(np.float32)

    settings.pop = len(columns['infected'])
    print( f"Population={settings.pop}" )
    settings.nodes = [ node for node in np.unique(columns['node']) ]
    settings.num_nodes = len(settings.nodes)
    print( f"Nodes={settings.num_nodes}" )
    # Now 'columns' is a dictionary where keys are column headers and values are NumPy arrays
    def eula():
        # test out what happens if we render big chunks of the population epi-borrowing
        condition = np.logical_and(~columns['infected'], columns['age']>15)
        columns['immunity'][condition] = 1
        columns['immunity_timer'][condition] = -1
    eula()
    return columns

def initialize_database():
    return load( settings.pop_file )
    
def eula( df, age_threshold_yrs = 5, eula_strategy=None ):
    # Create a boolean mask for elements to keep
    def filter_strategy():
        # test out what happens if we render big chunks of the population epi-borrowing
        condition = np.logical_and(~columns['infected'], columns['age']>15)
        columns['immunity'][condition] = 1
        columns['immunity_timer'][condition] = -1

    def purge_strategy():
        mask = (df['age'] <= age_threshold_yrs) | (df['infected'] != 0)
        for column in df.keys():
            df[column] = df[column][mask]
    purge_strategy()
    return df

def collect_report( data ):
    """
    Report data to file for a given timestep.
    """
    #print( "Start timestep report." )
    def collect_report_np():
        condition_mask = np.logical_and(~data['infected'], ~data['immunity'])
        unique_nodes, counts = np.unique(data['node'][condition_mask], return_counts=True)

        # Display the result
        susceptible_counts_db = list(zip(unique_nodes, counts))
        susceptible_counts = {values[0]: values[1] for idx, values in enumerate(susceptible_counts_db)}
        for node in settings.nodes:
            if node not in susceptible_counts:
                susceptible_counts[node] = 0

        unique_nodes, counts = np.unique(data['node'][data['infected']], return_counts=True)
        infected_counts_db = list(zip(unique_nodes, counts))
        infected_counts = {values[0]: values[1] for idx, values in enumerate(infected_counts_db)}
        for node in settings.nodes:
            if node not in infected_counts:
                infected_counts[node] = 0

        unique_nodes, counts = np.unique(data['node'][data['immunity']], return_counts=True)
        recovered_counts_db  = list(zip(unique_nodes, counts))
        recovered_counts = {values[0]: values[1] for idx, values in enumerate(recovered_counts_db)}
        for node in settings.nodes:
            if node not in recovered_counts:
                recovered_counts[node] = 0

        #print( "Stop timestep report." )
        return infected_counts, susceptible_counts, recovered_counts 

    return collect_report_np()

def update_ages( data ):
    @numba.jit(parallel=True,nopython=True)
    def update_ages_nb( ages ):
        n = len(ages)
        for i in range(n):
            ages[i] += 1/365
        return ages
        #data['age'] += 1/365
    def update_ages_np( ages ):
        ages += 1/365
        return ages

    data['age'] = update_ages_np( data['age'] )
    data = update_births_deaths( data )
    return data

def births(data):
    # Births
    # Calculate number of women of child-bearing age: constant across nodes
    # Add new babies as percentage of that.

    # Create a boolean mask for the age condition
    age_condition_mask = (data['age'] > 15) & (data['age'] < 45)

    # Filter data based on the age condition
    filtered_nodes = data['node'][age_condition_mask]
    filtered_ages  = data['age'][age_condition_mask]

    # Calculate the count of data per node and divide by 2
    unique_nodes, counts = np.unique(filtered_nodes, return_counts=True)
    wocba = np.column_stack((unique_nodes, counts // 2))

    # Create a dictionary from the wocba array
    wocba_dict = dict(wocba)

    # Function to add newborns
    def add_newborns(node, babies):
        # Generate newborn data
        last_id = data['id'][-1]
        new_ids = np.arange(last_id + 1, last_id + 1 + babies)
        new_nodes = np.full(babies, node)
        new_ages = np.zeros(babies)
        new_infected = np.full(babies,False)
        new_infection_timer = np.zeros(babies)
        new_incubation_timer = np.zeros(babies)
        new_immunity = np.full(babies,False)
        new_immunity_timer = np.zeros(babies)
        new_expected_lifespan = np.random.normal(loc=75, scale=7, size=babies)

        # Append newborns to arrays
        data['id'] = np.concatenate((data['id'], new_ids))
        data['node'] = np.concatenate((data['node'], new_nodes))
        data['age'] = np.concatenate((data['age'], new_ages))
        data['infected'] = np.concatenate((data['infected'], new_infected))
        data['infection_timer'] = np.concatenate((data['infection_timer'], new_infection_timer))
        data['incubation_timer'] = np.concatenate((data['incubation_timer'], new_incubation_timer))
        data['immunity'] = np.concatenate((data['immunity'], new_immunity))
        data['immunity_timer'] = np.concatenate((data['immunity_timer'], new_immunity_timer))
        data['expected_lifespan'] = np.concatenate((data['expected_lifespan'], new_expected_lifespan))

    # Iterate over nodes and add newborns
    for node, count in wocba_dict.items():
        new_babies = np.sum(np.random.rand(count) < 2.7e-4)
        if new_babies > 0:
            add_newborns(node, new_babies)

    return data

def deaths(data):
    # Non-disease deaths
    # Create a boolean mask for the deletion condition
    delete_mask = data['age'] >= data['expected_lifespan']

    for col in data:
        #data['infected'] = np.delete( data['infected'], np.where( delete_mask ) )
        data[col] = np.delete( data[col], np.where( delete_mask ) )

    print( f"{len(delete_mask)} new deaths." )
    return data

def update_births_deaths( data ):
    data = births(data)
    data = deaths(data)
    return data

def progress_infections( data ):
    # Update infected agents
    # infection timer: decrement for each infected person
    def progress_infections_np( data ):
        data['infection_timer'][data['infection_timer'] >= 1] -= 1
        data['incubation_timer'][data['incubation_timer'] >= 1] -= 1
        # some people clear
        condition = np.logical_and(data['infected'], data['infection_timer'] == 0)
        data['infected'][condition] = False
        # recovereds gain immunity
        data['immunity_timer'][condition] = np.random.randint(10, 41, size=np.sum(condition))
        data['immunity'][condition] = True

    progress_infections_np( data )
    return data

# Update immune agents
def progress_immunities( data ):
    def progress_immunities_np( data ):
        # immunity decays
        condition = np.logical_and(data['immunity'], data['immunity_timer'] > 0)
        data['immunity_timer'][condition] -= 1
        # Recoverd->Susceptible
        condition = np.logical_and(data['immunity'], data['immunity_timer'] == 0)
        data['immunity'][condition] = False

    progress_immunities_np( data )
    return data

def calculate_new_infections( data, inf, sus ):
    def calculate_new_infections_np( data, inf, sus ):
        # We want to count the number of incubators by now all at once not in a for loop.
        node_counts_incubators = np.zeros(len(inf))
        node_counts_incubators = np.bincount( data['node'][data['incubation_timer']>=1] )
        if len( node_counts_incubators ) == 0:
            print( "node_counts_incubators came back size 0." ) # this can be OK at the beginning.
            node_counts_incubators = np.zeros( settings.num_nodes )
        elif len( node_counts_incubators ) != len( inf ):
            #print( "node_counts_incubators came back missing a node." )
            node_counts_incubators = np.pad( node_counts_incubators, (0, len(inf)-len(node_counts_incubators) ), 'constant', constant_values=0 )

        sorted_items = sorted(inf.items())
        inf_np = np.array([value for _, value in sorted_items])
        if inf_np.shape != node_counts_incubators.shape:
            raise RuntimeError( f"inf_np shape ({inf_np.shape}) has different size from node_counts_incubators ({node_counts_incubators.shape})." )
        foi = (inf_np-node_counts_incubators) * settings.base_infectivity
        sus_np = np.array(list(sus.values()))
        new_infections = (foi * sus_np).astype(int)
        #print( new_infections )
        return new_infections
     
    return calculate_new_infections_np( data, inf, sus )

def handle_transmission_by_node( data, new_infections, node=0 ):
    # Step 5: Update the infected flag for NEW infectees
    def handle_new_infections(new_infections):
        # print( f"We are doing transmission to {new_infections} in node {node}." )
        # Create a boolean mask based on the conditions in the subquery
        subquery_condition = np.logical_and(~data['infected'], ~data['immunity'])
        subquery_condition = np.logical_and(subquery_condition, (data['node'] == node))

        # Get the indices of eligible agents using the boolean mask
        eligible_agents_indices = np.where(subquery_condition)[0]

        # Randomly sample 'new_infections' number of indices
        selected_indices = np.random.choice(eligible_agents_indices, size=min(new_infections, len(eligible_agents_indices)), replace=False)

        # Update the 'infected' column based on the selected indices
        data['infected'][selected_indices] = True
        #data['incubation_timer'][selected_indices] = 2

    #print( new_infections[node] )
    if new_infections[node]>0:
        handle_new_infections(new_infections[node])

    #print( f"{new_infections} new infections in node {node}." )
    return data

def handle_transmission( data_in, new_infections_in ):
    # We want to do this in parallel;
    htbn = partial( handle_transmission_by_node, data_in, new_infections_in )
    with concurrent.futures.ThreadPoolExecutor() as executor:
        results = list(executor.map(htbn, settings.nodes))
    return data_in

def add_new_infections( data ):
    # Actually this just sets the new infection timers (globally) for all the new infections
    # New infections themselves are set node-wise
    def add_new_infections_np( data ):
        condition = np.logical_and(data['infected'], data['infection_timer'] == 0)
        data['infection_timer'][condition] = np.random.randint(4, 15, size=np.sum(condition))
        data['incubation_timer'][condition] = 2
        return data

    data = add_new_infections_np( data )
    return data

def migrate( data, timestep, num_infected=None ):
    # Migrate 1% of infecteds "downstream" every week; coz
    if timestep % 7 == 0: # every week
        def migrate_np():
            infected = np.where( data['infected'] )[0]
            fraction = int(len(infected)*0.01)
            selected = np.random.choice( infected, fraction )
            # Update the 'nodes' array based on the specified conditions
            data['node'][selected] = np.where(data['node'][selected] - 1 < 0, settings.num_nodes - 1, data['node'][selected] - 1 )

        migrate_np()
    return data

def distribute_interventions( ctx, timestep ):
    def ria_9mo():
        condition_mask = (
            (ctx['age'] > 290/365.0) &
            (ctx['age'] < 291/365.0) &
            (ctx['immunity'] == 0) &
            (ctx['node'] == 15)
        )

        # Apply the update using the boolean mask
        ctx['immunity'][condition_mask] = 1
        ctx['immunity_timer'][condition_mask] = 3650
 
    def campaign( coverage = 1.0 ):
        # Create a boolean mask for the conditions specified in the WHERE clause
        condition_mask = (
            (ctx['immunity'] == 0) &
            (ctx['age'] < 16) &
            (ctx['node'] == 15)
        )

        # Shuffle the array to simulate ORDER BY RANDOM()
        #np.random.shuffle(ctx[condition_mask])

        # Get the indices of elements that satisfy the condition
        selected_indices = np.where(condition_mask)[0]

        # Calculate the number of elements to select based on the specified coverage
        num_to_select = int(len(selected_indices) * coverage)

        # Randomly select X% of indices
        selected_indices_subset = np.random.choice(selected_indices, size=num_to_select, replace=False)

        # Calculate the limit based on the specified coverage
        #limit = int(np.sum(condition_mask) * coverage)

        # Apply the update to the limited subset
        ctx['immunity'][selected_indices_subset] = 1
        ctx['immunity_timer'][selected_indices_subset] = -1

    ria_9mo()
    if timestep == 60:
        campaign()
    return ctx

# Function to run the simulation for a given number of timesteps
def run_simulation(data, csvwriter, num_timesteps):
    currently_infectious, currently_sus, cur_reco  = collect_report( data )
    report.write_timestep_report( csvwriter, 0, currently_infectious, currently_sus, cur_reco )

    for timestep in range(1, num_timesteps + 1):
        data = update_ages( data )

        data = progress_infections( data )

        data = progress_immunities( data )

        new_infections = calculate_new_infections( data, currently_infectious, currently_sus )

        data = handle_transmission( data_in=data, new_infections_in=new_infections )

        data = add_new_infections( data )

        data = migrate( data, timestep )

        currently_infectious, currently_sus, cur_reco = collect_report( data )
        report.write_timestep_report( csvwriter, timestep, currently_infectious, currently_sus, cur_reco )


    print("Simulation completed. Report saved to 'simulation_report.csv'.")

# Main simulation
if __name__ == "__main__":
    data = initialize_database()

    # Create a CSV file for reporting
    csvfile = open('simulation_report.csv', 'w', newline='') 
    csvwriter = csv.writer(csvfile)
    csvwriter.writerow(['Timestep', 'Node', 'Susceptible', 'Infected', 'Recovered'])

    # Run the simulation for 1000 timesteps
    run_simulation(data, csvwriter, num_timesteps=settings.duration )

