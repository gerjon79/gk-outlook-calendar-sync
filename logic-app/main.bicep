// One calendar sync pair: a Logic App (Consumption) that mirrors the events of a source Outlook calendar as
// SyncBlocker events into a destination Outlook calendar, using the sync helper Container App.
// The two Office 365 connections are created unauthenticated; the calendar owner must authorize them once.

@description('Short, unique name of this sync pair, e.g. "gerjon-rawworks-to-interstellar". Used in resource names.')
param pairName string

@description('Label of the destination account (calendar 1), shown on the connection, e.g. "gerjon@interstellar.nl".')
param destinationAccountLabel string

@description('Label of the source account (calendar 2), shown on the connection, e.g. "gerjon@rawworks.nl".')
param sourceAccountLabel string

@description('Name of the destination calendar as the Outlook API returns it, e.g. "Agenda" or "Calendar".')
param destinationCalendarName string

@description('Name of the source calendar as the Outlook API returns it, e.g. "Agenda" or "Calendar".')
param sourceCalendarName string

@description('If true, the workflow only computes the actions and does not modify the destination calendar.')
param dryRun bool = true

@description('Whether the Logic App runs on its schedule. Keep false until both connections are authorized.')
param enabled bool = false

@description('Additional workflow settings to override, keyed by variable name (see the parameters in workflow.json).')
param settings object = {}

param location string = resourceGroup().location
param containerAppName string = 'outlook-sync'
param apiKeySecretName string = 'api-key'

resource syncHelper 'Microsoft.App/containerApps@2024-03-01' existing = {
  name: containerAppName
}

var office365ApiId = subscriptionResourceId('Microsoft.Web/locations/managedApis', location, 'office365')

resource destinationConnection 'Microsoft.Web/connections@2016-06-01' = {
  name: 'outlook-${pairName}-destination'
  location: location
  properties: {
    displayName: 'Destination: ${destinationAccountLabel}'
    api: {
      id: office365ApiId
    }
  }
}

resource sourceConnection 'Microsoft.Web/connections@2016-06-01' = {
  name: 'outlook-${pairName}-source'
  location: location
  properties: {
    displayName: 'Source: ${sourceAccountLabel}'
    api: {
      id: office365ApiId
    }
  }
}

var baseParameters = {
  '$connections': {
    value: {
      outlookDestination: {
        connectionId: destinationConnection.id
        connectionName: destinationConnection.name
        id: office365ApiId
      }
      outlookSource: {
        connectionId: sourceConnection.id
        connectionName: sourceConnection.name
        id: office365ApiId
      }
    }
  }
  syncHelperServerUrl: {
    value: 'https://${syncHelper.properties.configuration.ingress.fqdn}/v1'
  }
  syncHelperApiKey: {
    value: filter(syncHelper.listSecrets().value, s => s.name == apiKeySecretName)[0].value
  }
  nameCalendar1: {
    value: destinationCalendarName
  }
  nameCalendar2: {
    value: sourceCalendarName
  }
  dryRun: {
    value: dryRun
  }
}

resource workflow 'Microsoft.Logic/workflows@2019-05-01' = {
  name: 'calendar-sync-${pairName}'
  location: location
  properties: {
    state: enabled ? 'Enabled' : 'Disabled'
    definition: loadJsonContent('workflow.json')
    parameters: union(baseParameters, toObject(items(settings), s => s.key, s => { value: s.value }))
  }
}

output workflowName string = workflow.name
output destinationConnectionName string = destinationConnection.name
output sourceConnectionName string = sourceConnection.name
