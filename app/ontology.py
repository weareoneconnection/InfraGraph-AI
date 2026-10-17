from __future__ import annotations

CLASSES = {
 'Project':['project','项目'],
 'Asset':['pier','bridge','station','tunnel','road','asset','墩','桥','车站','隧道','道路','构件'],
 'Drawing':['drawing','图纸'],
 'Specification':['specification','standard','规范','标准'],
 'WorkPackage':['work package','工作包'],
 'MethodStatement':['method statement','施工方案','方法书'],
 'Inspection':['inspection','itp','检查','检验'],
 'NCR':['ncr','non-conformance','不符合项'],
 'RFI':['rfi','request for information','技术澄清'],
 'ContractClause':['clause','contract','合同','条款'],
 'Variation':['variation','change order','变更','签证'],
 'Claim':['claim','eot','索赔','工期延长'],
 'Hazard':['hazard','risk','safety','危险源','风险','安全'],
 'Permit':['permit','approval','许可','审批'],
 'Authority':['authority','dosh','cidb','主管机关'],
 'CorrectiveAction':['corrective action','rectification','整改','纠正措施'],
 'Verification':['verification','verify','核验','验证'],
 'LessonLearned':['lesson learned','经验教训'],
 'ScheduleActivity':['schedule','activity','programme','进度','活动'],
 'CostItem':['cost','valuation','budget','费用','计价','预算'],
 'Sensor':['sensor','telemetry','传感器','遥测'],
 'MaintenanceTask':['maintenance','维护','检修'],
}

RELATION_RULES = [
 ('Asset','GOVERNED_BY','Specification'),
 ('WorkPackage','USES','MethodStatement'),
 ('Inspection','DETECTS','NCR'),
 ('NCR','RESOLVED_BY','CorrectiveAction'),
 ('CorrectiveAction','CONFIRMED_BY','Verification'),
 ('Variation','IMPACTS','CostItem'),
 ('Variation','IMPACTS','ScheduleActivity'),
 ('Claim','SUPPORTED_BY','ContractClause'),
 ('Permit','ISSUED_BY','Authority'),
 ('MaintenanceTask','MONITORS','Sensor'),
]
