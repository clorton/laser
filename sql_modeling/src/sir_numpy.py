import random
import csv
import numpy as np
import concurrent.futures
from functools import partial
import pdb

import settings
import report

# Globals! (not really)
#base_infectivity = 0.000002
settings.base_infectivity = 0.00001

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
    columns['node'] = columns['node'].astype(int)

    settings.pop = len(columns['infected'])
    print( f"Population={settings.pop}" )
    settings.nodes = [ node for node in np.unique(columns['node']) ]
    settings.num_nodes = len(settings.nodes)
    print( f"Nodes={settings.num_nodes}" )
    # Now 'columns' is a dictionary where keys are column headers and values are NumPy arrays
    return columns

def initialize_database():
    return load( settings.pop_file )
    
def collect_report( data ):
    """
    Report data to file for a given timestep.
    """
    #print( "Start timestep report." )
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

def update_ages( data ):
    data['age'] += 1/365
    return data

def progress_infections( data ):
    #pdb.set_trace()
    # Update infected agents
    # infection timer: decrement for each infected person
    data['infection_timer'][data['infection_timer'] >= 1] -= 1
    data['incubation_timer'][data['incubation_timer'] >= 1] -= 1
    # some people clear
    condition = np.logical_and(data['infected'], data['infection_timer'] == 0)
    data['infected'][condition] = False
    # recovereds gain immunity
    data['immunity_timer'][condition] = np.random.randint(10, 41, size=np.sum(condition))
    data['immunity'][condition] = True
    return data

# Update immune agents
def progress_immunities( data ):
    # immunity decays
    condition = np.logical_and(data['immunity'], data['immunity_timer'] > 0)
    data['immunity_timer'][condition] -= 1
    # Recoverd->Susceptible
    condition = np.logical_and(data['immunity'], data['immunity_timer'] == 0)
    data['immunity'][condition] = False
    return data

def calculate_new_infections( data, inf, sus ):
    # We want to count the number of incubators by now all at once not in a for loop.
    node_counts_incubators = np.bincount( data['node'][data['incubation_timer']>=1] )
    if len( node_counts_incubators ) == 0:
        print( "node_counts_incubators came back size 0." )
        node_counts_incubators = np.zeros( settings.num_nodes )
        #raise ValueError( "node_counts_incubators came back size 0." )
    sorted_items = sorted(inf.items())
    inf_np = np.array([value for _, value in sorted_items])
    foi = (inf_np-node_counts_incubators) * settings.base_infectivity
    sus_np = np.array(list(sus.values()))
    new_infections = (foi * sus_np).astype(int)
    #print( new_infections )
    return new_infections

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
        data['incubation_timer'][selected_indices] = 2

    #print( new_infections[node] )
    if new_infections[node]>0:
        handle_new_infections(new_infections[node])
        #handle_new_infections(new_infections)

    #print( f"{new_infections} new infections in node {node}." )
    return data

def handle_transmission( data_in, new_infections_in ):
    #print( "handle_transmission" )
    # We want to do this in parallel
    htbn = partial( handle_transmission_by_node, data_in, new_infections_in )
    with concurrent.futures.ThreadPoolExecutor() as executor:
        results = list(executor.map(htbn, settings.nodes))
        #results = list(executor.map(handle_new_infections_np, settings.nodes))
    return data_in

def add_new_infections( data ):
    # Actually this just sets the new infection timers (globally) for all the new infections
    # New infections themselves are set node-wise
    condition = np.logical_and(data['infected'], data['infection_timer'] == 0)
    data['infection_timer'][condition] = np.random.randint(4, 15, size=np.sum(condition))
    return data

def migrate( data, timestep, num_infected=None ):
    if timestep % 7 == 0: # every week
        infected = np.where( data['infected'] )[0]
        fraction = int(len(infected)*0.01)
        selected = np.random.choice( infected, fraction )
        # Update the 'nodes' array based on the specified conditions
        data['node'][selected] = np.where(data['node'][selected] - 1 < 0, settings.num_nodes - 1, data['node'][selected] - 1 )
    return data

# Function to run the simulation for a given number of timesteps
def run_simulation(data, csvwriter, num_timesteps):
    currently_infectious, currently_sus, cur_reco  = report( data )
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
    data = load()

    # Create a CSV file for reporting
    csvfile = open('simulation_report.csv', 'w', newline='') 
    csvwriter = csv.writer(csvfile)
    csvwriter.writerow(['Timestep', 'Node', 'Susceptible', 'Infected', 'Recovered'])

    # Run the simulation for 1000 timesteps
    run_simulation(data, csvwriter, num_timesteps=settings.duration )

