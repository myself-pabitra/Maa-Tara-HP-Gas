
#Generate a list of all possible combinations of a given list of elements

def generate_combinations(elements):
    if not elements:
        return [[]]
    
    first = elements[0]
    rest = elements[1:]
    
    combinations_without_first = generate_combinations(rest)
    combinations_with_first = [[first] + combo for combo in combinations_without_first]
    
    return combinations_without_first + combinations_with_first

# Example usage
elements = [1, 2, 3]
combinations = generate_combinations(elements)
for combo in combinations:
    print(combo)
