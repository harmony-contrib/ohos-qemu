@Entry
@Component
struct Index {
  @LocalStorageLink('diagnostic') private diagnostic: string = 'OpenVPN QA awaiting actual request';
  build() { Column() {
    Text('OpenVPN cleanup QA: no connected or traffic claim')
    Text(this.diagnostic).id('openvpn-qa-actual-diagnostic')
  }.width('100%').height('100%') }
}
