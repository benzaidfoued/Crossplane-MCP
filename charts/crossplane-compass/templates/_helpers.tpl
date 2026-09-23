{{- define "compass.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- define "compass.fullname" -}}
{{- default (printf "%s-%s" .Release.Name (include "compass.name" .)) .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- define "compass.sa" -}}
{{- default (include "compass.fullname" .) .Values.serviceAccount.name -}}
{{- end -}}
{{- define "compass.labels" -}}
app.kubernetes.io/name: {{ include "compass.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
