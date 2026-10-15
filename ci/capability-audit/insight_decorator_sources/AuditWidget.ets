let storage: LocalStorage = new LocalStorage();
@Entry(storage)
@Component
struct AuditWidget {
  @LocalStorageProp('runId') runId: string = 'unbound';
  @LocalStorageProp('formId') formId: string = 'unbound';
  @LocalStorageProp('state') state: string = 'unbound';
  build() {
    Column() {
      Text(this.runId + ':' + this.formId + ':' + this.state)
        .fontSize(12).id('insight-form-widget-data')
    }.width('100%').height('100%').backgroundColor('#ddeeff')
  }
}
