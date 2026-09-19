use crate::model::Task;
use serde::Deserialize;
use std::collections::{HashMap, HashSet};

#[derive(Deserialize)]
pub struct Relationships {
    pub parent_ids: Vec<String>,
    pub dependency_ids: Vec<String>,
    pub expected_parent_ids: Vec<String>,
    pub expected_dependency_ids: Vec<String>,
}

fn same(a: &[String], b: &[String]) -> bool {
    a.iter().collect::<HashSet<_>>() == b.iter().collect::<HashSet<_>>()
}
impl Relationships {
    pub fn unchanged_since(&self, task: &Task) -> bool {
        same(&self.expected_parent_ids, &task.parent_ids)
            && same(&self.expected_dependency_ids, &task.dependency_ids)
    }
    pub fn validate(&mut self, task: &Task, tasks: &[Task]) -> Result<(), String> {
        if self.parent_ids.len() > 1 || self.dependency_ids.len() > 200 {
            return Err("Choose at most one parent and 200 prerequisites".into());
        }
        self.dependency_ids.sort();
        self.dependency_ids.dedup();
        let by_id: HashMap<_, _> = tasks.iter().map(|t| (t.id.as_str(), t)).collect();
        for (label, ids, hierarchy) in [
            ("Hierarchy", &self.parent_ids, true),
            ("Dependency", &self.dependency_ids, false),
        ] {
            for id in ids {
                if id == &task.id {
                    return Err(format!("{label}: a task cannot reference itself"));
                }
                let target = by_id
                    .get(id.as_str())
                    .ok_or_else(|| format!("{label}: task unavailable: {id}"))?;
                if target.source != task.source || target.table_id != task.table_id {
                    return Err(
                        "Relationships must reference tasks in the same source table".into(),
                    );
                }
                let mut pending = vec![(id.as_str(), vec![task.title.as_str()])];
                let mut visited = HashSet::new();
                while let Some((current, mut path)) = pending.pop() {
                    if current == task.id {
                        path.push(&task.title);
                        return Err(format!("{label} cycle: {}", path.join(" → ")));
                    }
                    if !visited.insert(current) {
                        continue;
                    }
                    if let Some(t) = by_id.get(current) {
                        path.push(&t.title);
                        let links = if hierarchy {
                            &t.parent_ids
                        } else {
                            &t.dependency_ids
                        };
                        pending.extend(links.iter().map(|next| (next.as_str(), path.clone())));
                    }
                }
            }
        }
        Ok(())
    }
}

/// Only report actual cycle members, rather than every task downstream of a cycle.
pub fn cycle_members(tasks: &[Task], hierarchy: bool) -> Vec<String> {
    let by_id: HashMap<_, _> = tasks.iter().map(|t| (t.id.as_str(), t)).collect();
    tasks
        .iter()
        .filter(|task| {
            let links = |t: &Task| {
                if hierarchy {
                    t.parent_ids.clone()
                } else {
                    t.dependency_ids.clone()
                }
            };
            let mut pending = links(task);
            let mut visited = HashSet::new();
            while let Some(id) = pending.pop() {
                if id == task.id {
                    return true;
                }
                if visited.insert(id.clone())
                    && let Some(t) = by_id.get(id.as_str())
                {
                    pending.extend(links(t));
                }
            }
            false
        })
        .map(|t| t.id.clone())
        .collect()
}
