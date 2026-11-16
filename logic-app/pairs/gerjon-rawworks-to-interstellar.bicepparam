using '../main.bicep'

// Pilot: Rawworks calendar (source) -> Interstellar calendar (destination)
param pairName = 'gerjon-rawworks-to-interstellar'
param destinationAccountLabel = 'Gerjon (Interstellar)'
param sourceAccountLabel = 'Gerjon (Rawworks)'
param destinationCalendarName = 'Agenda'
param sourceCalendarName = 'Calendar'
param dryRun = true
param enabled = false
