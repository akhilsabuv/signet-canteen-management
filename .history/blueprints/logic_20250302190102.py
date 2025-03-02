// Function to load all required data
function loadData():
    // Load User Data from biostar2_db to the user db
    userData = loadUserDataFromBiostar2()
    storeUserDataInDB(userData)
    
    // Load Canteen timings from CSV to our db
    canteenTimings = loadCSV("canteen_timings.csv")
    storeCanteenTimingsInDB(canteenTimings)
    
    // Load Shift timings from CSV to our db
    shiftTimings = loadCSV("shift_timings.csv")
    storeShiftTimingsInDB(shiftTimings)
    
    // Load and select canteen devices and entry devices into our db
    canteenDevices = loadCanteenDevices()
    entryDevices = loadEntryDevices()
    storeDevicesInDB(canteenDevices, entryDevices)
    
    // Map shift timings to canteen timings
    mapShiftTimingsToCanteenTimings(shiftTimings, canteenTimings)


// Function to check if eligibility logic should run
function checkEligibilityLogic(dbValue, deviceType):
    // If the database count/value has changed
    if dbValueHasChanged(dbValue):
        // And if the device is a canteen device
        if deviceType == "canteen":
            // Run the eligibility check
            runEligibilityCheckForUser()


// Function to run the eligibility check process for a given user
function runEligibilityCheckForUser(user, currentCanteenTiming):
    // Step 1: Check if user has already taken a coupon for the same timing
    if hasUserTakenCoupon(user, currentCanteenTiming):
        displayError("User has already taken a coupon for this timing.")
        return

    // Step 2: Check entries for the user with an offset of -1 day and +1 day
    entries = getUserEntries(user, offsetDays=[-1, +1])

    // Step 3: Validate if any entry matches the required shift timing criteria
    if entryMatchesShiftTiming(entries, currentCanteenTiming):
        // Insert data to the coupon table in our DB
        couponToken = insertCouponRecord(user, currentCanteenTiming)
        
        // Print or generate the coupon with a unique token number
        printCoupon(couponToken)
        
        // Display success message (e.g., in a green box)
        displaySuccess("Coupon generated successfully.")
    else:
        // If no matching entry is found, display an error with details
        displayError("Eligibility criteria not met for the current timing.")


// Main Program Flow
function main():
    // Step 1: Load all necessary data
    loadData()
    
    // Step 2: Monitor the DB value for changes and determine device type
    dbValue = getCurrentDBValue()
    deviceType = getCurrentDeviceType()  // e.g., "canteen" or "entry"
    
    // Step 3: If conditions are met, run the eligibility check process
    checkEligibilityLogic(dbValue, deviceType)


// Execute the main function to start the process
main()