import random
import csv
import numpy as np
import pdb

# Globals! (not really)
#pop = 1000000
#pop = int(5e5)
num_nodes = 200
nodes = [ x for x in range(num_nodes) ]
duration = 365 # 1000
#base_infectivity = 0.00001
base_infectivity = 0.0004

def load():

    # Replace 'your_file.csv' with the actual path to your CSV file
    csv_file = 'pop_500k_200nodes.csv'

    # Load the entire CSV file into a NumPy array
    header_row = np.genfromtxt(csv_file, delimiter=',', dtype=str, max_rows=1)

    # Load the remaining data as numerical values, skipping the header row
    data = np.genfromtxt(csv_file, delimiter=',', dtype=float, skip_header=1)

    # Extract headers from the header row
    headers = header_row

    # Load each column into a separate NumPy array
    columns = {header: data[:, i] for i, header in enumerate(headers)}
    columns['infected'] = columns['infected'].astype(bool)
    columns['immunity'] = columns['immunity'].astype(bool)
    # Now 'columns' is a dictionary where keys are column headers and values are NumPy arrays
    return columns

    
def report( data, timestep, csvwriter ):
    print( "Start report." )
    # cursor.execute('SELECT node, COUNT(*) FROM agents WHERE NOT infected AND NOT immunity GROUP BY node')
    # this seems slow and clunky

    condition_mask = np.logical_and(~data['infected'], ~data['immunity'])
    unique_nodes, counts = np.unique(data['node'][condition_mask], return_counts=True)

    # Display the result
    susceptible_counts_db = list(zip(unique_nodes, counts))
    susceptible_counts = {values[0]: values[1] for idx, values in enumerate(susceptible_counts_db)}
    for node in nodes:
        if node not in susceptible_counts:
            susceptible_counts[node] = 0

    unique_nodes, counts = np.unique(data['node'][data['infected']], return_counts=True)
    infected_counts_db = list(zip(unique_nodes, counts))
    #cursor.execute('SELECT node, COUNT(*) FROM agents WHERE infected GROUP BY node')
    infected_counts = {values[0]: values[1] for idx, values in enumerate(infected_counts_db)}
    for node in nodes:
        if node not in infected_counts:
            infected_counts[node] = 0

    #cursor.execute('SELECT node, COUNT(*) FROM agents WHERE immunity GROUP BY node')
    #recovered_counts_db = cursor.fetchall()
    unique_nodes, counts = np.unique(data['node'][data['immunity']], return_counts=True)
    recovered_counts_db  = list(zip(unique_nodes, counts))
    recovered_counts = {values[0]: values[1] for idx, values in enumerate(recovered_counts_db)}
    for node in nodes:
        if node not in recovered_counts:
            recovered_counts[node] = 0

    # Write the counts to the CSV file
    print( f"T={timestep}, S={susceptible_counts}, I={infected_counts}, R={recovered_counts}" )
    for node in nodes:
        csvwriter.writerow([timestep,
            node,
            susceptible_counts[node] if node in susceptible_counts else 0,
            infected_counts[node] if node in infected_counts else 0,
            recovered_counts[node] if node in recovered_counts else 0,
            ]
        )
    print( "Stop report." )
    return infected_counts, susceptible_counts

# Function to run the simulation for a given number of timesteps
def run_simulation(data, csvwriter, num_timesteps):
    currently_infectious, currently_sus = report( data, 0, csvwriter )


    for timestep in range(1, num_timesteps + 1):
        # Update infected agents
        # infection timer: decrement for each infected person

        def update_ages():
            cursor.execute("UPDATE agents SET age = age+1/365")
        def update_ages_np():
            data['age'] += 1/365
        update_ages_np()
        #print( "Back from...update_ages()" )
        #print( f"update_ages took {age_time}" )

        def progress_infections():
            # Progress Existing Infections
            # Clear Recovereds
            # infected=0, immunity=1, immunity_timer=30-ish
            cursor.execute( "UPDATE agents SET infection_timer = (infection_timer-1) WHERE infection_timer>=1" )
            cursor.execute( "UPDATE agents SET incubation_timer = (incubation_timer-1) WHERE incubation_timer>=1" )
            cursor.execute( "UPDATE agents SET infected=False, immunity=1, immunity_timer=FLOOR(10+30*(RANDOM() + 9223372036854775808)/18446744073709551616) WHERE infected=True AND infection_timer=0" )
        def progress_infections_np():
            data['infection_timer'][data['infection_timer'] >= 1] -= 1
            data['incubation_timer'][data['incubation_timer'] >= 1] -= 1
            condition = np.logical_and(data['infected'], data['infection_timer'] == 0)
            data['infected'][condition] = False
            data['immunity_timer'][condition] = np.random.randint(10, 41, size=np.sum(condition))

        #progress_infections()
        progress_infections_np()
        #print( "Back from...progress_infections()" )

        # Update immune agents
        def progress_immunities():
            # immunity timer: decrement for each immune person
            # immunity flag: clear for each new sus person
            cursor.execute("UPDATE agents SET immunity_timer = (immunity_timer-1) WHERE immunity=1 AND immunity_timer>0" )
            cursor.execute("UPDATE agents SET immunity = 0 WHERE immunity = 1 AND immunity_timer=0" )
        def progress_immunities_np():
            condition = np.logical_and(data['immunity'], data['immunity_timer'] > 0)
            data['immunity_timer'][condition] -= 1
            condition = np.logical_and(data['immunity'], data['immunity_timer'] == 0)
            data['immunity'][condition] = False

        progress_immunities_np()
        #print( "Back from...progress_immunities()" )

        def handle_transmission( node=0 ):
            # Step 1: Calculate the number of currently infected
            #incubating_count = cursor.execute('SELECT COUNT(*) FROM agents WHERE incubation_timer >= 1 and node=:node', { 'node': node }).fetchone()[0]
            condition = np.logical_and(data['incubation_timer'] >= 1, data['node'] == node)
            #pdb.set_trace()

            # Use the boolean mask to filter data and calculate the count
            incubating_count = np.sum(condition)

            # Step 2: Calculate the force of infection (foi)
            if node in currently_infectious:
                if( incubating_count > currently_infectious[node] ):
                    print( f"incubating = {incubating_count} found to be > currently_infectious = {currently_infectious[node]} in node {node}!" )
                    pdb.set_trace()
                    raise ValueError( f"incubating = {incubating_count} found to be > currently_infectious = {currently_infectious[node]} in node {node}!" )
                foi = base_infectivity  * (currently_infectious[node]-incubating_count)  # Adjust the multiplier as needed
            else:
                foi = 0
            #foi = 0.0000009 * (currently_infectious[node]-incubating)  # Adjust the multiplier as needed
            #foi = 0.9 * pop * (currently_infectious[node]-incubating)  # Adjust the multiplier as needed

            # Step 4: Calculate the number of new infections (NEW)
            if node in currently_sus:
                new_infections = int(foi * currently_sus[node])
            else:
                new_infections = 0

            #print( f"{new_infections} new infections based on foi of {foi} and susceptible cout of {currently_sus}" )

            # Step 5: Update the infected flag for NEW infectees
            def new_infections_my_way():
                cursor.execute('''
                    UPDATE agents
                    SET infected = True
                    WHERE id IN (SELECT id FROM agents WHERE NOT infected AND NOT immunity AND node=:node ORDER BY RANDOM() LIMIT :new_infections)
                ''', {'new_infections': new_infections, 'node': node })
            def new_infections_chat_way():
                cursor.execute('''
                    UPDATE agents
                    SET infected = True
                    FROM (
                            SELECT id
                            FROM agents
                            WHERE NOT infected AND NOT immunity AND node = :node
                            ORDER BY RANDOM() LIMIT :new_infections
                            ) AS subquery
                    WHERE agents.id = subquery.id
                    ''', {'new_infections': new_infections, 'node': node } )
            def new_infections_np():
                # Create a boolean mask based on the conditions in the subquery
                subquery_condition = np.logical_and(~data['infected'], ~data['immunity'], data['node'] == node)

                # Get the indices of eligible agents using the boolean mask
                eligible_agents_indices = np.where(subquery_condition)[0]

                # Randomly sample 'new_infections' number of indices
                selected_indices = np.random.choice(eligible_agents_indices, size=min(new_infections, len(eligible_agents_indices)), replace=False)

                # Update the 'infected' column based on the selected indices
                data['infected'][selected_indices] = True
            new_infections_np()

            #print( f"{new_infections} new infections in node {node}." )

        for node in nodes:
            handle_transmission( node )
            #print( "Back from...handle_transmission()" )
            # handle new infectees, set new infection timer
            #cursor.execute( "UPDATE agents SET infection_timer=FLOOR(4+10*(RANDOM() + 9223372036854775808)/18446744073709551616) WHERE infected AND infection_timer=0" )
            condition = np.logical_and(data['infected'], data['infection_timer'] == 0)
            data['infection_timer'][condition] = np.random.randint(4, 15, size=np.sum(condition))
            #print( "Back from...init_inftimers()" )

        def migrate():
            if timestep % 7 == 0: # every week
                cursor.execute( '''
                    UPDATE agents SET node = CASE
                        WHEN node-1 < 0 THEN :max_node
                        ELSE node - 1
                    END
                    WHERE id IN (
                        SELECT id
                            FROM agents
                            WHERE RANDOM() <= 0.1  -- Select 10% of the rows randomly
                        )
                    ''', { 'max_node': num_nodes-1 } )
        def migrate_np():
            # Create a boolean mask based on the conditions in the subquery
            subquery_condition = np.random.random(size=len(data['id'])) <= 0.1

            # Get the indices of eligible agents using the boolean mask
            eligible_agents_indices = np.where(subquery_condition)[0]

            # Update the 'nodes' array based on the specified conditions
            data['node'][eligible_agents_indices] = np.where(data['node'][eligible_agents_indices] - 1 < 0, num_nodes - 1, data['node'][eligible_agents_indices] - 1)

        #migrate():
        migrate_np()

        #conn.commit()
        #print( "Back from...commit()" )
        #print( f"{cursor.execute('select * from agents where infected limit 25').fetchall()}".replace("), ",")\n") )
        #print( "*****" )
        currently_infectious, currently_sus = report( data, timestep, csvwriter )



    print("Simulation completed. Report saved to 'simulation_report.csv'.")

# Main simulation
if __name__ == "__main__":
    data = load()

    # Create a CSV file for reporting
    csvfile = open('simulation_report.csv', 'w', newline='') 
    csvwriter = csv.writer(csvfile)
    csvwriter.writerow(['Timestep', 'Node', 'Susceptible', 'Infected', 'Recovered'])

    # Run the simulation for 1000 timesteps
    run_simulation(data, csvwriter, num_timesteps=duration )

