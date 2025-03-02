def load_data():
    """Load all required data from various sources into the database."""
    # Load User Data from biostar2_db to the user db
    user_data = load_user_data_from_biostar2()
    store_user_data_in_db(user_data)
    
    # Load Canteen timings from CSV to our db
    canteen_timings = load_csv("canteen_timings.csv")
    store_canteen_timings_in_db(canteen_timings)
    
    # Load Shift timings from CSV to our db
    shift_timings = load_csv("shift_timings.csv")
    store_shift_timings_in_db(shift_timings)
    
    # Load and select canteen devices and entry devices into our db
    canteen_devices = load_canteen_devices()
    entry_devices = load_entry_devices()
    store_devices_in_db(canteen_devices, entry_devices)
    
    # Map shift timings to canteen timings
    map_shift_timings_to_canteen_timings(shift_timings, canteen_timings)


def check_eligibility_logic(db_value, device_type):
    """Check if eligibility logic should run based on db value changes and device type."""
    # If the database count/value has changed
    if db_value_has_changed(db_value):
        # And if the device is a canteen device
        if device_type == "canteen":
            # Run the eligibility check
            run_eligibility_check_for_user()


def run_eligibility_check_for_user(user, current_canteen_timing):
    """Run the eligibility check process for a given user."""
    # Step 1: Check if user has already taken a coupon for the same timing
    if has_user_taken_coupon(user, current_canteen_timing):
        display_error("User has already taken a coupon for this timing.")
        return

    # Step 2: Check entries for the user with an offset of -1 day and +1 day
    entries = get_user_entries(user, offset_days=[-1, +1])

    # Step 3: Validate if any entry matches the required shift timing criteria
    if entry_matches_shift_timing(entries, current_canteen_timing):
        # Insert data to the coupon table in our DB
        coupon_token = insert_coupon_record(user, current_canteen_timing)
        
        # Print or generate the coupon with a unique token number
        print_coupon(coupon_token)
        
        # Display success message
        display_success("Coupon generated successfully.")
    else:
        # If no matching entry is found, display an error with details
        display_error("Eligibility criteria not met for the current timing.")


def main():
    """Main program flow."""
    # Step 1: Load all necessary data
    load_data()
    
    # Step 2: Monitor the DB value for changes and determine device type
    db_value = get_current_db_value()
    device_type = get_current_device_type()  # e.g., "canteen" or "entry"
    
    # Step 3: If conditions are met, run the eligibility check process
    check_eligibility_logic(db_value, device_type)


# Execute the main function to start the process
main()